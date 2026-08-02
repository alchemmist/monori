"""
Bank connections: one bank login per connection, owned by the user, with any.

number of accounts linked to it (``accounts.connection_id`` + a bank-specific.
``accounts.bank_ref`` locator). A sync logs in once and pulls every linked
account in turn, reusing the cached session between pulls.

There is no background scheduler — syncs run only when triggered here. A sync
that hits an OTP step returns ``status: awaiting_sms`` and stays parked in the
sync runner (in-process or in the standalone sync service, see
:mod:`app.sync_runner`) until the user posts the code to ``/sms``; the code
completes the parked account's pull and the remaining accounts follow on the
now-cached session.
"""

import logging
import secrets
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass as pydantic_dataclass

from app import crypto
from app.auth import AuthenticatedUser, current_user
from app.connectors import base as connectors
from app.connectors.base import (
    ConnectorError,
    ConnectorInfo,
    JsonObject,
    SmsRequiredError,
    SyncResult,
    SyncRow,
)
from app.deps import conn
from app.importer import CategoryDefinition, CategoryRule, build_rules
from app.ingest import categorize_rows, commit_rows, drop_already_present, historical_day_counts
from app.sync_runner import NoPendingLoginError, SyncRequest, get_runner
from app.transfer_service import detect

router = APIRouter(prefix="/api/connections", tags=["connections"])

log = logging.getLogger(__name__)

SMS_SENT = "A confirmation code was sent to your phone."
CODE_REJECTED = "The bank rejected the code — check it and try again."
SYNC_FAILED = "The bank sync could not be completed. Check the connection and try again."


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class ConnectionBody:
    """Represent ConnectionBody."""

    bank: str
    kind: str
    credentials: JsonObject


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class SmsBody:
    """Represent SmsBody."""

    code: str


@dataclass(slots=True)
class ConnectionRow:
    """Represent ConnectionRow."""

    id: int
    bank: str
    kind: str
    credentials_encrypted: bytes | memoryview | None
    session_encrypted: bytes | memoryview | None
    last_sync: str | None
    pending_account_id: int | None
    status: str
    last_error: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class LinkedAccount:
    """Represent LinkedAccount."""

    id: int
    name: str
    bank_ref: str | None


@dataclass(slots=True)
class SyncContext:
    """Represent shared state for a connection sync."""

    connection: sqlite3.Connection
    row: ConnectionRow
    credentials: JsonObject
    session: JsonObject | None
    user_id: int


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class AccountSyncSummary:
    """Represent AccountSyncSummary."""

    inserted: int
    skipped: int
    account_id: int = Field(serialization_alias="accountId")
    batch_id: int | None = Field(serialization_alias="batchId")
    date_from: str | None = Field(serialization_alias="dateFrom")
    date_to: str | None = Field(serialization_alias="dateTo")


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class UnmappedTail:
    """Represent UnmappedTail."""

    tail: str
    rows: int


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class SyncResponse:
    """Represent SyncResponse."""

    status: str
    inserted: int
    skipped: int
    accounts: list[AccountSyncSummary]
    date_from: str | None = Field(serialization_alias="dateFrom")
    date_to: str | None = Field(serialization_alias="dateTo")
    unmapped_tails: list[UnmappedTail] = Field(serialization_alias="unmappedTails")


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class SyncStatusResponse:
    """Represent SyncStatusResponse."""

    status: str
    message: str | None = None


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class ConnectionResponse:
    """Represent ConnectionResponse."""

    id: int
    bank: str
    kind: str
    status: str
    last_sync: str | None = Field(serialization_alias="lastSync", validation_alias="lastSync")
    last_error: str | None = Field(serialization_alias="lastError", validation_alias="lastError")
    has_credentials: bool = Field(
        serialization_alias="hasCredentials", validation_alias="hasCredentials"
    )
    created_at: str = Field(serialization_alias="createdAt", validation_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt", validation_alias="updatedAt")


def _optional_blob(value: sqlite3.Row, key: str) -> bytes | memoryview | None:
    raw = value[key]
    return raw if isinstance(raw, (bytes, memoryview)) else None


def _optional_str(value: sqlite3.Row, key: str) -> str | None:
    raw = value[key]
    return raw if isinstance(raw, str) else None


def _optional_int(value: sqlite3.Row, key: str) -> int | None:
    raw = value[key]
    return raw if isinstance(raw, int) else None


def _load(c: sqlite3.Connection, cid: int, uid: int) -> ConnectionRow:
    row = c.execute(
        "SELECT * FROM bank_connections WHERE id=? AND user_id=?",
        (cid, uid),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "unknown connection")
    return ConnectionRow(
        id=int(row["id"]),
        bank=str(row["bank"]),
        kind=str(row["kind"]),
        credentials_encrypted=_optional_blob(row, "credentials_encrypted"),
        session_encrypted=_optional_blob(row, "session_encrypted"),
        last_sync=_optional_str(row, "last_sync"),
        pending_account_id=_optional_int(row, "pending_account_id"),
        status=str(row["status"]),
        last_error=_optional_str(row, "last_error"),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _serialize_connection(row: ConnectionRow) -> ConnectionResponse:
    return ConnectionResponse(
        id=row.id,
        bank=row.bank,
        kind=row.kind,
        status=row.status,
        last_sync=row.last_sync,
        last_error=row.last_error,
        has_credentials=row.credentials_encrypted is not None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _linked_accounts(c: sqlite3.Connection, cid: int, uid: int) -> list[LinkedAccount]:
    return [
        LinkedAccount(int(r["id"]), str(r["name"]), _optional_str(r, "bank_ref"))
        for r in c.execute(
            "SELECT id, name, bank_ref FROM accounts"
            " WHERE connection_id=? AND user_id=? ORDER BY sort, id",
            (cid, uid),
        )
    ]


def _load_user_rules(c: sqlite3.Connection, uid: int) -> dict[str, list[CategoryRule]]:
    groups = {
        r["id"]: r["kind"]
        for r in c.execute(
            "SELECT g.id, t.type AS kind FROM category_groups g"
            " JOIN category_group_types t ON t.id=g.type_id WHERE g.user_id=?",
            (uid,),
        )
    }
    cats: list[CategoryDefinition] = [
        CategoryDefinition(
            id=int(r["id"]),
            name=str(r["name"]),
            keywords=str(r["keywords"]) if r["keywords"] is not None else None,
            group_id=int(r["group_id"]),
        )
        for r in c.execute(
            "SELECT c.id, c.name, c.keywords, c.group_id FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=? ORDER BY c.sort",
            (uid,),
        )
    ]
    return build_rules(cats, groups)


def _require_crypto() -> None:
    if not crypto.available():
        raise HTTPException(400, "MONORI_ENCRYPTION_KEY is not set; bank connections are disabled")


def _validate_credentials(bank: str, kind: str, credentials: JsonObject) -> None:
    try:
        cls = connectors.get_connector_class(bank, kind)
    except ConnectorError as e:
        raise HTTPException(400, str(e)) from e
    missing = [
        p.name
        for p in getattr(cls, "connection_params", [])
        if p.required and not str(credentials.get(p.name) or "").strip()
    ]
    if missing:
        raise HTTPException(400, f"missing credentials: {missing}")


def _require_account_refs(row: ConnectionRow, accounts: list[LinkedAccount]) -> None:
    """
    Handle A connector that declares required account params cannot sync an account.

    without its bank_ref — the pull would silently fall back to the default.
    feed and land another account's operations here.
    """
    try:
        cls = connectors.get_connector_class(row.bank, row.kind)
    except ConnectorError:
        return
    if not any(p.required for p in getattr(cls, "account_params", [])):
        return
    unset = [a.name for a in accounts if not (a.bank_ref or "").strip()]
    if unset:
        raise HTTPException(400, f"these accounts need a bank account id before syncing: {unset}")


def _mark_error(c: sqlite3.Connection, cid: int, message: str) -> None:
    c.execute(
        "UPDATE bank_connections SET status='error', last_error=?, pending_account_id=NULL,"
        " updated_at=? WHERE id=?",
        (message, _now(), cid),
    )
    c.commit()


def _fail(c: sqlite3.Connection, cid: int, error: Exception) -> NoReturn:
    """
    Record a failed sync and surface it to the client without leaking the raw.

    connector error: the detail is logged, the user sees a fixed message.
    """
    log.warning("bank connection %s sync failed: %s", cid, error)
    _mark_error(c, cid, SYNC_FAILED)
    raise HTTPException(502, SYNC_FAILED) from error


def _card_digits(card: str) -> str:
    return "".join(ch for ch in card if ch.isdigit())


def _match_tail(bound: Mapping[str, set[int]], digits: str) -> str | None:
    """
    Handle The bound tail that identifies this card, by mutual suffix (a 4-digit.

    statement tail must still match a longer stored tail and vice versa).
    The longest — most specific — matching tail wins.
    """
    matches = [t for t in bound if digits.endswith(t) or t.endswith(digits)]
    return max(matches, key=len) if matches else None


def _route_rows(
    c: sqlite3.Connection,
    uid: int,
    default_account_id: int,
    rows: list[SyncRow],
) -> tuple[dict[int, list[SyncRow]], dict[str, int]]:
    """
    Split synced rows between the user's accounts by their bound card tails.

    (``accounts.card_tails``). Rows whose tail is not bound anywhere — or is.
    bound to several accounts, which makes routing ambiguous — stay on the
    synced account; when the feed mixes several cards, those tails are
    reported back so the user can fix the bindings instead of silently merging.
    """
    bound: dict[str, set[int]] = {}
    for r in c.execute("SELECT id, card_tails FROM accounts WHERE user_id=? ORDER BY id", (uid,)):
        for t in str(r["card_tails"] or "").split(","):
            if t:
                bound.setdefault(t, set()).add(int(r["id"]))
    routed: dict[int, list[SyncRow]] = {}
    unmapped: dict[str, int] = {}
    seen_tails = set()
    for row in rows:
        digits = _card_digits(row.card)
        tail = digits[-4:]
        if tail:
            seen_tails.add(tail)
        matched = _match_tail(bound, digits) if digits else None
        owners = bound.get(matched, set()) if matched else set()
        if len(owners) == 1:
            target = next(iter(owners))
        else:
            target = default_account_id
            if tail:
                unmapped[tail] = unmapped.get(tail, 0) + 1
        routed.setdefault(target, []).append(row)
    if len(seen_tails) <= 1:
        unmapped = {}
    return routed, unmapped


def _finish_account(
    c: sqlite3.Connection,
    row: ConnectionRow,
    account_id: int,
    result: SyncResult,
    uid: int,
) -> tuple[list[AccountSyncSummary], dict[str, int]]:
    """
    Categorize, route rows to their bound accounts (falling back to the synced.

    account), commit each slice as its own batch, cache the session. Returns.
    (per-account summaries, unmapped card tails).
    """
    rules = _load_user_rules(c, uid)
    categorize_rows(result.rows, rules)

    rows, redelivered = drop_already_present(result.rows, historical_day_counts(c, uid))
    routed, unmapped = _route_rows(c, uid, account_id, rows)

    routed.setdefault(account_id, [])
    summaries: list[AccountSyncSummary] = []
    for target_id, rows in sorted(routed.items(), key=lambda kv: kv[0] != account_id):
        cur = c.execute(
            "INSERT INTO import_batches (account_id, connection_id, source, created_at)"
            " VALUES (?, ?, 'sync', ?)",
            (target_id, row.id, _now()),
        )
        batch_id = cur.lastrowid
        inserted, skipped = commit_rows(c, target_id, rows, source="sync", batch_id=batch_id)
        if target_id == account_id:
            skipped += redelivered
        c.execute(
            "UPDATE import_batches SET inserted=?, skipped=? WHERE id=?",
            (inserted, skipped, batch_id),
        )
        dates = sorted(r.date for r in rows)
        summaries.append(
            AccountSyncSummary(
                account_id=target_id,
                inserted=inserted,
                skipped=skipped,
                batch_id=batch_id,
                date_from=dates[0] if dates else None,
                date_to=dates[-1] if dates else None,
            ),
        )
    session = getattr(result, "session", None)
    if session:
        c.execute(
            "UPDATE bank_connections SET session_encrypted=?, updated_at=? WHERE id=?",
            (crypto.encrypt(session), _now(), row.id),
        )

    detect(c, uid)
    c.commit()
    return summaries, unmapped


def _mark_connected(c: sqlite3.Connection, cid: int) -> None:
    c.execute(
        "UPDATE bank_connections SET status='connected', last_sync=?, last_error=NULL,"
        " pending_account_id=NULL, updated_at=? WHERE id=?",
        (_now(), _now(), cid),
    )
    c.commit()


def _aggregate(
    results: list[AccountSyncSummary],
    unmapped: dict[str, int] | None = None,
) -> SyncResponse:
    dates_from = [r.date_from for r in results if r.date_from is not None]
    dates_to = [r.date_to for r in results if r.date_to is not None]
    return SyncResponse(
        status="connected",
        inserted=sum(r.inserted for r in results),
        skipped=sum(r.skipped for r in results),
        accounts=results,
        date_from=min(dates_from) if dates_from else None,
        date_to=max(dates_to) if dates_to else None,
        unmapped_tails=[UnmappedTail(tail=t, rows=n) for t, n in sorted((unmapped or {}).items())],
    )


def _account_since(
    c: sqlite3.Connection,
    cid: int,
    account_id: int,
    last_sync: str | None,
) -> str | None:
    """
    Handle An account newly linked to an already-synced connection still needs a.

    full pull: the connection's last_sync cursor only applies to accounts that.
    have synced through it before.
    """
    if last_sync is None:
        return None
    prior = c.execute(
        "SELECT 1 FROM import_batches WHERE connection_id=? AND account_id=?"
        " AND source='sync' LIMIT 1",
        (cid, account_id),
    ).fetchone()
    return last_sync if prior else None


def _sync_accounts(
    context: SyncContext,
    accounts: list[LinkedAccount],
) -> tuple[list[AccountSyncSummary], dict[str, int]]:
    """
    Pull each account in order. Returns (per-account summaries, unmapped card.

    tails); raises SmsRequiredError after persisting which account the parked login.
    belongs to.
    """
    c = context.connection
    row = context.row
    cid = row.id
    results: list[AccountSyncSummary] = []
    unmapped: dict[str, int] = {}
    for acct in accounts:
        try:
            result = get_runner().start(
                SyncRequest(
                    cid,
                    row.bank,
                    row.kind,
                    context.credentials,
                    context.session,
                    _account_since(c, cid, acct.id, row.last_sync),
                    acct.bank_ref,
                ),
            )
        except SmsRequiredError:
            c.execute(
                "UPDATE bank_connections SET status='awaiting_sms', pending_account_id=?,"
                " updated_at=? WHERE id=?",
                (acct.id, _now(), cid),
            )
            c.commit()
            raise
        summaries, missed = _finish_account(c, row, acct.id, result, context.user_id)
        results.extend(summaries)
        for t, n in missed.items():
            unmapped[t] = unmapped.get(t, 0) + n
        context.session = result.session or context.session
    return results, unmapped


@router.get("/available")
def available(_user: Annotated[AuthenticatedUser, Depends(current_user)]) -> list[ConnectorInfo]:
    """Handle available."""
    return connectors.available_connectors()


@router.post("")
def create_connection(
    body: ConnectionBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> ConnectionResponse:
    """Handle create connection."""
    _require_crypto()
    uid = user.id
    _validate_credentials(body.bank, body.kind, body.credentials)
    c = conn()
    try:
        creds_dict = dict(body.credentials)

        creds_dict["code"] = f"{secrets.randbelow(10000):04d}"
        creds = crypto.encrypt(creds_dict)
        cur = c.execute(
            "INSERT INTO bank_connections (user_id, bank, kind, credentials_encrypted,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, body.bank, body.kind, creds, _now(), _now()),
        )
        c.commit()
        connection_id = cur.lastrowid
        if connection_id is None:
            msg = "inserted connection did not return a row id"
            raise RuntimeError(msg)
        return _serialize_connection(_load(c, connection_id, uid))
    finally:
        c.close()


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class CredentialsPatch:
    """Represent CredentialsPatch."""

    credentials: JsonObject


@router.patch("/{cid}")
def update_credentials(
    cid: int,
    body: CredentialsPatch,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> ConnectionResponse:
    """Handle update credentials."""
    _require_crypto()
    uid = user.id
    c = conn()
    try:
        row = _load(c, cid, uid)
        _validate_credentials(row.bank, row.kind, body.credentials)
        creds_dict = dict(body.credentials)
        creds_dict["code"] = f"{secrets.randbelow(10000):04d}"
        c.execute(
            "UPDATE bank_connections SET credentials_encrypted=?, session_encrypted=NULL,"
            " status='disconnected', updated_at=? WHERE id=?",
            (crypto.encrypt(creds_dict), _now(), cid),
        )
        c.commit()
        return _serialize_connection(_load(c, cid, uid))
    finally:
        c.close()


@router.delete("/{cid}")
def delete_connection(
    cid: int,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> dict[str, int]:
    """Handle delete connection."""
    uid = user.id
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
def cancel_sync(
    cid: int,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> dict[str, int]:
    """
    Abandon a login waiting for its OTP: close the parked connector and drop.

    the connection out of the awaiting_sms state.
    """
    uid = user.id
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
def sync_connection(
    cid: int,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SyncResponse | SyncStatusResponse:
    """Handle sync connection."""
    _require_crypto()
    uid = user.id
    c = conn()
    try:
        row = _load(c, cid, uid)
        accounts = _linked_accounts(c, cid, uid)
        if not accounts:
            raise HTTPException(400, "no accounts are linked to this connection")
        _require_account_refs(row, accounts)
        creds = crypto.decrypt(row.credentials_encrypted)
        if not creds:
            raise HTTPException(400, "connection has no credentials")
        if not creds.get("code"):
            creds["code"] = f"{secrets.randbelow(10000):04d}"
            c.execute(
                "UPDATE bank_connections SET credentials_encrypted=? WHERE id=?",
                (crypto.encrypt(creds), cid),
            )
            c.commit()
        session = crypto.decrypt(row.session_encrypted)
        try:
            results, unmapped = _sync_accounts(
                SyncContext(c, row, creds, session, uid),
                accounts,
            )
            _mark_connected(c, cid)
            return _aggregate(results, unmapped)
        except SmsRequiredError:
            return SyncStatusResponse(status="awaiting_sms", message=SMS_SENT)
        except ConnectorError as e:
            _fail(c, cid, e)
    finally:
        c.close()


@router.post("/{cid}/sms")
def submit_sms(
    cid: int,
    body: SmsBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SyncResponse | SyncStatusResponse:
    """Handle submit sms."""
    _require_crypto()
    uid = user.id
    c = conn()
    try:
        row = _load(c, cid, uid)
        accounts = _linked_accounts(c, cid, uid)
        pending_id = (
            row.pending_account_id
            if row.pending_account_id is not None
            else (accounts[0].id if accounts else None)
        )
        if pending_id is None:
            raise HTTPException(400, "no accounts are linked to this connection")
        try:
            result = get_runner().resume(cid, body.code)
        except NoPendingLoginError as e:
            raise HTTPException(409, "no login awaiting a code") from e
        except SmsRequiredError:
            return SyncStatusResponse(status="awaiting_sms", message=CODE_REJECTED)
        except ConnectorError as e:
            _fail(c, cid, e)
        results, unmapped = _finish_account(c, row, pending_id, result, uid)
        session = result.session or crypto.decrypt(row.session_encrypted)
        ids = [a.id for a in accounts]
        after = ids.index(pending_id) + 1 if pending_id in ids else len(ids)
        remaining = accounts[after:]
        try:
            more, missed = _sync_accounts(
                SyncContext(c, row, _creds(row), session, uid),
                remaining,
            )
        except SmsRequiredError:
            return SyncStatusResponse(status="awaiting_sms", message=SMS_SENT)
        except ConnectorError as e:
            _fail(c, cid, e)
        results.extend(more)
        for t, n in missed.items():
            unmapped[t] = unmapped.get(t, 0) + n
        _mark_connected(c, cid)
        return _aggregate(results, unmapped)
    finally:
        c.close()


def _creds(row: ConnectionRow) -> JsonObject:
    creds = crypto.decrypt(row.credentials_encrypted)
    if not creds:
        raise HTTPException(400, "connection has no credentials")
    return creds
