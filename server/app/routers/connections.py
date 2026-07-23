"""Bank connections: one bank login per connection, owned by the user, with any
number of accounts linked to it (``accounts.connection_id`` + a bank-specific
``accounts.bank_ref`` locator). A sync logs in once and pulls every linked
account in turn, reusing the cached session between pulls.

There is no background scheduler — syncs run only when triggered here. A sync
that hits an OTP step returns ``status: awaiting_sms`` and stays parked in the
sync runner (in-process or in the standalone sync service, see
:mod:`app.sync_runner`) until the user posts the code to ``/sms``; the code
completes the parked account's pull and the remaining accounts follow on the
now-cached session.
"""

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
from ..sync_runner import NoPendingLogin, get_runner

router = APIRouter(prefix="/api/connections", tags=["connections"])


def _now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class ConnectionBody(BaseModel):
    bank: str
    kind: str
    credentials: dict


class SmsBody(BaseModel):
    code: str


def _load(c, cid, uid):
    row = c.execute(
        "SELECT * FROM bank_connections WHERE id=? AND user_id=?", (cid, uid)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "unknown connection")
    return row


def _linked_accounts(c, cid, uid):
    return [
        dict(r)
        for r in c.execute(
            "SELECT id, name, bank_ref FROM accounts"
            " WHERE connection_id=? AND user_id=? ORDER BY sort, id",
            (cid, uid),
        )
    ]


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


def _validate_credentials(bank, kind, credentials):
    try:
        cls = connectors.get_connector_class(bank, kind)
    except ConnectorError as e:
        raise HTTPException(400, str(e)) from e
    missing = [
        p["name"]
        for p in getattr(cls, "connection_params", [])
        if p.get("required") and not str(credentials.get(p["name"]) or "").strip()
    ]
    if missing:
        raise HTTPException(400, f"missing credentials: {missing}")


def _mark_error(c, cid, message):
    c.execute(
        "UPDATE bank_connections SET status='error', last_error=?, pending_account_id=NULL,"
        " updated_at=? WHERE id=?",
        (message, _now(), cid),
    )
    c.commit()


def _finish_account(c, row, account_id, result, uid):
    """Categorize, commit one account's rows as a batch, cache the session."""
    rules = _load_user_rules(c, uid)
    categorize_rows(result.rows, rules)
    cur = c.execute(
        "INSERT INTO import_batches (account_id, connection_id, source, created_at)"
        " VALUES (?, ?, 'sync', ?)",
        (account_id, row["id"], _now()),
    )
    batch_id = cur.lastrowid
    inserted, skipped = commit_rows(c, account_id, result.rows, source="sync", batch_id=batch_id)
    c.execute(
        "UPDATE import_batches SET inserted=?, skipped=? WHERE id=?",
        (inserted, skipped, batch_id),
    )
    if result.session:
        c.execute(
            "UPDATE bank_connections SET session_encrypted=?, updated_at=? WHERE id=?",
            (crypto.encrypt(result.session), _now(), row["id"]),
        )
    c.commit()
    dates = sorted(r["date"] for r in result.rows)
    return {
        "accountId": account_id,
        "inserted": inserted,
        "skipped": skipped,
        "batchId": batch_id,
        "dateFrom": dates[0] if dates else None,
        "dateTo": dates[-1] if dates else None,
    }


def _mark_connected(c, cid):
    c.execute(
        "UPDATE bank_connections SET status='connected', last_sync=?, last_error=NULL,"
        " pending_account_id=NULL, updated_at=? WHERE id=?",
        (_now(), _now(), cid),
    )
    c.commit()


def _aggregate(results):
    dates_from = [r["dateFrom"] for r in results if r["dateFrom"]]
    dates_to = [r["dateTo"] for r in results if r["dateTo"]]
    return {
        "status": "connected",
        "inserted": sum(r["inserted"] for r in results),
        "skipped": sum(r["skipped"] for r in results),
        "accounts": results,
        "dateFrom": min(dates_from) if dates_from else None,
        "dateTo": max(dates_to) if dates_to else None,
    }


def _account_since(c, cid, account_id, last_sync):
    """An account newly linked to an already-synced connection still needs a
    full pull: the connection's last_sync cursor only applies to accounts that
    have synced through it before."""
    if last_sync is None:
        return None
    prior = c.execute(
        "SELECT 1 FROM import_batches WHERE connection_id=? AND account_id=?"
        " AND source='sync' LIMIT 1",
        (cid, account_id),
    ).fetchone()
    return last_sync if prior else None


def _sync_accounts(c, row, accounts, creds, session, uid):
    """Pull each account in order. Returns per-account summaries; raises
    SmsRequired after persisting which account the parked login belongs to."""
    cid = row["id"]
    results = []
    for acct in accounts:
        try:
            result = get_runner().start(
                cid,
                row["bank"],
                row["kind"],
                creds,
                session,
                _account_since(c, cid, acct["id"], row["last_sync"]),
                acct["bank_ref"] or None,
            )
        except SmsRequired:
            c.execute(
                "UPDATE bank_connections SET status='awaiting_sms', pending_account_id=?,"
                " updated_at=? WHERE id=?",
                (acct["id"], _now(), cid),
            )
            c.commit()
            raise
        results.append(_finish_account(c, row, acct["id"], result, uid))
        session = result.session or session
    return results


@router.get("/available")
def available(user: Annotated[dict, Depends(current_user)]):
    return connectors.available_connectors()


@router.post("")
def create_connection(body: ConnectionBody, user: Annotated[dict, Depends(current_user)]):
    _require_crypto()
    uid = user["id"]
    _validate_credentials(body.bank, body.kind, body.credentials)
    c = conn()
    try:
        creds_dict = dict(body.credentials)
        # a quick-login code we set on the bank's "create a code" screen after the
        # first OTP, then reuse to log in on later syncs without another SMS
        creds_dict["code"] = f"{secrets.randbelow(10000):04d}"
        creds = crypto.encrypt(creds_dict)
        cur = c.execute(
            "INSERT INTO bank_connections (user_id, bank, kind, credentials_encrypted,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, body.bank, body.kind, creds, _now(), _now()),
        )
        c.commit()
        return serialize_connection(_load(c, cur.lastrowid, uid))
    finally:
        c.close()


class CredentialsPatch(BaseModel):
    credentials: dict


@router.patch("/{cid}")
def update_credentials(
    cid: int, body: CredentialsPatch, user: Annotated[dict, Depends(current_user)]
):
    _require_crypto()
    uid = user["id"]
    c = conn()
    try:
        row = _load(c, cid, uid)
        _validate_credentials(row["bank"], row["kind"], body.credentials)
        creds_dict = dict(body.credentials)
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
        get_runner().cancel(cid)
        c.execute("UPDATE accounts SET connection_id=NULL WHERE connection_id=?", (cid,))
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
        get_runner().cancel(cid)
        c.execute(
            "UPDATE bank_connections SET status='disconnected', pending_account_id=NULL,"
            " updated_at=? WHERE id=? AND status='awaiting_sms'",
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
        accounts = _linked_accounts(c, cid, uid)
        if not accounts:
            raise HTTPException(400, "no accounts are linked to this connection")
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
        try:
            results = _sync_accounts(c, row, accounts, creds, session, uid)
            _mark_connected(c, cid)
            return _aggregate(results)
        except SmsRequired as e:
            return {"status": "awaiting_sms", "message": str(e)}
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
        accounts = _linked_accounts(c, cid, uid)
        pending_id = row["pending_account_id"] or (accounts[0]["id"] if accounts else None)
        if pending_id is None:
            raise HTTPException(400, "no accounts are linked to this connection")
        try:
            result = get_runner().resume(cid, body.code)
        except NoPendingLogin as e:
            raise HTTPException(409, "no login awaiting a code") from e
        except SmsRequired as e:
            return {"status": "awaiting_sms", "message": str(e)}
        except ConnectorError as e:
            _mark_error(c, cid, str(e))
            raise HTTPException(502, str(e)) from e
        results = [_finish_account(c, row, pending_id, result, uid)]
        session = result.session or crypto.decrypt(row["session_encrypted"])
        ids = [a["id"] for a in accounts]
        after = ids.index(pending_id) + 1 if pending_id in ids else len(ids)
        remaining = accounts[after:]
        try:
            results.extend(_sync_accounts(c, row, remaining, _creds(c, row), session, uid))
        except SmsRequired as e:
            return {"status": "awaiting_sms", "message": str(e)}
        except ConnectorError as e:
            _mark_error(c, cid, str(e))
            raise HTTPException(502, str(e)) from e
        _mark_connected(c, cid)
        return _aggregate(results)
    finally:
        c.close()


def _creds(c, row):
    creds = crypto.decrypt(row["credentials_encrypted"])
    if not creds:
        raise HTTPException(400, "connection has no credentials")
    return creds
