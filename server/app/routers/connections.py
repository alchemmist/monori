"""Bank connections: connect an account to a connector and sync it on demand.

There is no background scheduler — syncs run only when triggered here. A sync
that hits an OTP step returns ``status: awaiting_sms`` and parks the live
connector in ``PENDING`` (in-process; fine for a single-user self-hosted app)
until the user posts the code to ``/sms``.
"""

import contextlib
import secrets
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import crypto
from ..auth import current_user
from ..connectors import base as connectors
from ..connectors.base import ConnectorError, SmsRequired
from ..deps import conn, serialize_connection
from ..importer import build_rules
from ..ingest import categorize_rows, commit_rows

router = APIRouter(prefix="/api/connections", tags=["connections"])

# connection id -> a live connector mid-login, awaiting its OTP code
PENDING: dict[int, connectors.Connector] = {}


def _now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _close_pending(cid):
    """Drop and close any connector parked mid-login for this connection, so its
    browser/worker never leaks when the attempt is replaced, cancelled or the
    connection is deleted."""
    old = PENDING.pop(cid, None)
    if old is not None:
        with contextlib.suppress(Exception):
            old.close()


class Credentials(BaseModel):
    phone: str
    password: str


class ConnectionBody(BaseModel):
    accountId: int
    bank: str
    kind: str
    credentials: Credentials


class SmsBody(BaseModel):
    code: str


def _load(c, cid, uid):
    row = c.execute(
        "SELECT bc.* FROM bank_connections bc JOIN accounts a ON a.id = bc.account_id"
        " WHERE bc.id=? AND a.user_id=?",
        (cid, uid),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "unknown connection")
    return row


def _load_user_rules(c, uid):
    groups = {
        r["id"]: r["kind"]
        for r in c.execute("SELECT id, kind FROM category_groups WHERE user_id=?", (uid,))
    }
    cats = [
        dict(r)
        for r in c.execute(
            "SELECT c.id, c.name, c.keywords, c.group_id FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=? ORDER BY c.sort",
            (uid,),
        )
    ]
    return build_rules(cats, groups)


def _require_crypto():
    if not crypto.available():
        raise HTTPException(400, "MONORI_ENCRYPTION_KEY is not set; bank connections are disabled")


def _mark_error(c, cid, message):
    c.execute(
        "UPDATE bank_connections SET status='error', last_error=?, updated_at=? WHERE id=?",
        (message, _now(), cid),
    )
    c.commit()


def _finish(c, row, result, uid):
    """Categorize, commit as a batch, cache the session and mark connected."""
    rules = _load_user_rules(c, uid)
    categorize_rows(result.rows, rules)
    cur = c.execute(
        "INSERT INTO import_batches (account_id, connection_id, source, created_at)"
        " VALUES (?, ?, 'sync', ?)",
        (row["account_id"], row["id"], _now()),
    )
    batch_id = cur.lastrowid
    inserted, skipped = commit_rows(
        c, row["account_id"], result.rows, source="sync", batch_id=batch_id
    )
    c.execute(
        "UPDATE import_batches SET inserted=?, skipped=? WHERE id=?",
        (inserted, skipped, batch_id),
    )
    session_blob = crypto.encrypt(result.session) if result.session else row["session_encrypted"]
    c.execute(
        "UPDATE bank_connections SET session_encrypted=?, status='connected', last_sync=?,"
        " last_error=NULL, updated_at=? WHERE id=?",
        (session_blob, _now(), _now(), row["id"]),
    )
    c.commit()
    dates = sorted(r["date"] for r in result.rows)
    return {
        "status": "connected",
        "inserted": inserted,
        "skipped": skipped,
        "batchId": batch_id,
        "dateFrom": dates[0] if dates else None,
        "dateTo": dates[-1] if dates else None,
    }


@router.post("")
def create_connection(body: ConnectionBody, user: Annotated[dict, Depends(current_user)]):
    _require_crypto()
    uid = user["id"]
    c = conn()
    try:
        if not c.execute(
            "SELECT id FROM accounts WHERE id=? AND user_id=?", (body.accountId, uid)
        ).fetchone():
            raise HTTPException(400, "unknown account")
        try:
            connectors.get_connector_class(body.bank, body.kind)
        except ConnectorError as e:
            raise HTTPException(400, str(e)) from e
        creds_dict = body.credentials.model_dump()
        # a quick-login code we set on the bank's "create a code" screen after the
        # first OTP, then reuse to log in on later syncs without another SMS
        creds_dict["code"] = f"{secrets.randbelow(10000):04d}"
        creds = crypto.encrypt(creds_dict)
        cur = c.execute(
            "INSERT INTO bank_connections (account_id, bank, kind, credentials_encrypted,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (body.accountId, body.bank, body.kind, creds, _now(), _now()),
        )
        c.commit()
        return serialize_connection(_load(c, cur.lastrowid, uid))
    finally:
        c.close()


@router.patch("/{cid}")
def update_credentials(
    cid: int, credentials: Credentials, user: Annotated[dict, Depends(current_user)]
):
    _require_crypto()
    uid = user["id"]
    c = conn()
    try:
        _load(c, cid, uid)
        creds_dict = credentials.model_dump()
        creds_dict["code"] = f"{secrets.randbelow(10000):04d}"
        c.execute(
            "UPDATE bank_connections SET credentials_encrypted=?, session_encrypted=NULL,"
            " status='disconnected', updated_at=? WHERE id=?",
            (crypto.encrypt(creds_dict), _now(), cid),
        )
        c.commit()
        return serialize_connection(_load(c, cid, uid))
    finally:
        c.close()


@router.delete("/{cid}")
def delete_connection(cid: int, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        _load(c, cid, uid)
        _close_pending(cid)
        c.execute("DELETE FROM bank_connections WHERE id=?", (cid,))
        c.commit()
        return {"deleted": cid}
    finally:
        c.close()


@router.post("/{cid}/cancel")
def cancel_sync(cid: int, user: Annotated[dict, Depends(current_user)]):
    """Abandon a login waiting for its OTP: close the parked connector and drop
    the connection out of the awaiting_sms state."""
    uid = user["id"]
    c = conn()
    try:
        _load(c, cid, uid)
        _close_pending(cid)
        c.execute(
            "UPDATE bank_connections SET status='disconnected', updated_at=?"
            " WHERE id=? AND status='awaiting_sms'",
            (_now(), cid),
        )
        c.commit()
        return {"cancelled": cid}
    finally:
        c.close()


@router.post("/{cid}/sync")
def sync_connection(cid: int, user: Annotated[dict, Depends(current_user)]):
    _require_crypto()
    uid = user["id"]
    c = conn()
    try:
        row = _load(c, cid, uid)
        creds = crypto.decrypt(row["credentials_encrypted"])
        if not creds:
            raise HTTPException(400, "connection has no credentials")
        if not creds.get("code"):
            creds["code"] = f"{secrets.randbelow(10000):04d}"
            c.execute(
                "UPDATE bank_connections SET credentials_encrypted=? WHERE id=?",
                (crypto.encrypt(creds), cid),
            )
            c.commit()
        session = crypto.decrypt(row["session_encrypted"])
        # a re-triggered sync replaces any earlier attempt still parked on its OTP
        _close_pending(cid)
        cls = connectors.get_connector_class(row["bank"], row["kind"])
        connector = cls(creds, session)
        try:
            return _finish(c, row, connector.sync(row["last_sync"]), uid)
        except SmsRequired:
            PENDING[cid] = connector
            c.execute(
                "UPDATE bank_connections SET status='awaiting_sms', updated_at=? WHERE id=?",
                (_now(), cid),
            )
            c.commit()
            return {"status": "awaiting_sms"}
        except ConnectorError as e:
            _mark_error(c, cid, str(e))
            raise HTTPException(502, str(e)) from e
    finally:
        c.close()


@router.post("/{cid}/sms")
def submit_sms(cid: int, body: SmsBody, user: Annotated[dict, Depends(current_user)]):
    _require_crypto()
    uid = user["id"]
    c = conn()
    try:
        row = _load(c, cid, uid)
        connector = PENDING.pop(cid, None)
        if connector is None:
            raise HTTPException(409, "no login awaiting a code")
        try:
            return _finish(c, row, connector.resume_sync(body.code), uid)
        except ConnectorError as e:
            _mark_error(c, cid, str(e))
            raise HTTPException(502, str(e)) from e
    finally:
        c.close()
