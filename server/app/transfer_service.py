"""
The database side of transfers: merging two transactions into one entity,.

splitting them apart again, and running detection over a user's ledger.

Kept out of the router so the import and sync pipelines can merge freshly
ingested rows through exactly the same code path the UI uses.
"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from monori.server.app.db import begin_write
from monori.server.app.db_records import TransactionRecord, TransferRecord, TransferSplitRecord
from monori.server.app.transfer_match import (
    AUTO_DAYS,
    SUGGEST_DAYS,
    TransferCandidate,
    TransferMatchRow,
    find_pairs,
    split_confident,
)

LINKABLE_COLUMNS = (
    "SELECT t.id, t.date, t.amount, t.description, t.account_id, t.transfer_id"
    " FROM transactions t JOIN accounts a ON a.id = t.account_id"
    " WHERE a.user_id=? AND t.transfer_id IS NULL"
    " AND t.source != 'adjustment'"
)


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class TransferResponse:
    """Represent TransferResponse."""

    id: str
    origin: str
    note: str
    out_tx_id: int
    in_tx_id: int
    created_at: str


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class MergedTransfer:
    """Represent MergedTransfer."""

    id: str
    amount: int
    days: int
    hint: bool
    mismatch: bool
    out_tx_id: int
    in_tx_id: int


def serialize_transfer(record: TransferRecord) -> TransferResponse:
    """Handle serialize transfer."""
    return TransferResponse(
        id=record.id,
        out_tx_id=record.out_tx_id,
        in_tx_id=record.in_tx_id,
        origin=record.origin,
        note=record.note,
        created_at=record.created_at,
    )


def list_transfers(c: sqlite3.Connection, uid: int) -> list[TransferResponse]:
    """Handle list transfers."""
    return [
        serialize_transfer(TransferRecord.from_row(r))
        for r in c.execute(
            "SELECT id, out_tx_id, in_tx_id, origin, note, created_at FROM transfers"
            " WHERE user_id=? ORDER BY created_at DESC, id",
            (uid,),
        )
    ]


def owned_tx(c: sqlite3.Connection, uid: int, tx_id: int) -> TransactionRecord | None:
    """Handle owned tx."""
    row = c.execute(
        "SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id"
        " WHERE t.id=? AND a.user_id=?",
        (tx_id, uid),
    ).fetchone()
    return TransactionRecord.from_row(row) if row is not None else None


class LinkError(Exception):
    """Why a pair cannot become a transfer. The router turns it into a 400."""


@dataclass(frozen=True, slots=True)
class LinkRequest:
    """Represent the two transaction legs and metadata for a transfer."""

    out_tx_id: int
    in_tx_id: int
    origin: str = "manual"
    note: str = ""


def link(
    c: sqlite3.Connection,
    uid: int,
    request: LinkRequest,
) -> str:
    """
    Merge two existing transactions into a transfer. The rows are left in place.

    — only ``transfer_id`` is stamped and the categories are moved aside, so a.
    later split restores exactly what was there.
    """
    begin_write(c)
    out_row = owned_tx(c, uid, request.out_tx_id)
    in_row = owned_tx(c, uid, request.in_tx_id)
    if out_row is None or in_row is None:
        msg = "unknown transaction"
        raise LinkError(msg)
    if out_row.amount >= 0 or in_row.amount <= 0:
        msg = "a transfer needs one outflow and one inflow"
        raise LinkError(msg)
    if out_row.account_id == in_row.account_id:
        msg = "both legs are on the same account"
        raise LinkError(msg)
    if out_row.transfer_id or in_row.transfer_id:
        msg = "already part of a transfer"
        raise LinkError(msg)
    if c.execute(
        "SELECT 1 FROM splits WHERE transaction_id IN (?, ?) LIMIT 1",
        (request.out_tx_id, request.in_tx_id),
    ).fetchone():
        msg = "split transactions cannot be linked as a transfer"
        raise LinkError(msg)

    transfer_id = uuid.uuid4().hex

    try:
        c.execute(
            "INSERT INTO transfers"
            " (id, user_id, out_tx_id, in_tx_id, origin, out_category_id, in_category_id,"
            "  note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                transfer_id,
                uid,
                request.out_tx_id,
                request.in_tx_id,
                request.origin,
                out_row.category_id,
                in_row.category_id,
                request.note,
                datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        )
    except sqlite3.IntegrityError as e:
        msg = "already part of a transfer"
        raise LinkError(msg) from e
    c.execute(
        "UPDATE transactions SET transfer_id=?, category_id=NULL WHERE id IN (?, ?)",
        (transfer_id, request.out_tx_id, request.in_tx_id),
    )
    c.execute(
        "DELETE FROM transfer_rejections WHERE out_tx_id=? AND in_tx_id=?",
        (request.out_tx_id, request.in_tx_id),
    )
    return transfer_id


def split(c: sqlite3.Connection, uid: int, transfer_id: str) -> bool:
    """
    Undo a merge: both transactions stay, get their categories back and stop.

    pointing at the transfer. Returns False when the transfer is not the user's.
    """
    raw_row = c.execute(
        "SELECT out_tx_id, in_tx_id, out_category_id, in_category_id FROM transfers"
        " WHERE id=? AND user_id=?",
        (transfer_id, uid),
    ).fetchone()
    if raw_row is None:
        return False
    row = TransferSplitRecord.from_row(raw_row)
    c.execute(
        "UPDATE transactions SET transfer_id=NULL, category_id=? WHERE id=?",
        (row.out_category_id, row.out_tx_id),
    )
    c.execute(
        "UPDATE transactions SET transfer_id=NULL, category_id=? WHERE id=?",
        (row.in_category_id, row.in_tx_id),
    )
    c.execute("DELETE FROM transfers WHERE id=?", (transfer_id,))
    return True


def detach_leg(c: sqlite3.Connection, uid: int, tx_id: int) -> bool:
    """
    Split whatever transfer this transaction belongs to, so it can be deleted on.

    its own. Without this the entity row cascades away while the surviving leg.
    keeps a dangling ``transfer_id`` — and a dangling pointer reads as a transfer
    everywhere downstream, hiding a real transaction from every total.
    """
    row = c.execute(
        "SELECT id FROM transfers WHERE user_id=? AND (out_tx_id=? OR in_tx_id=?)",
        (uid, tx_id, tx_id),
    ).fetchone()
    if row is None:
        return False
    return split(c, uid, row["id"])


def reject(c: sqlite3.Connection, uid: int, out_tx_id: int, in_tx_id: int) -> None:
    """Remember that this pair is not a transfer, so detection stops proposing it."""
    if owned_tx(c, uid, out_tx_id) is None or owned_tx(c, uid, in_tx_id) is None:
        msg = "unknown transaction"
        raise LinkError(msg)
    c.execute(
        "INSERT OR IGNORE INTO transfer_rejections (out_tx_id, in_tx_id) VALUES (?, ?)",
        (out_tx_id, in_tx_id),
    )


def rejections(c: sqlite3.Connection, uid: int) -> set[tuple[int, int]]:
    """Handle rejections."""
    return {
        (r["out_tx_id"], r["in_tx_id"])
        for r in c.execute(
            "SELECT r.out_tx_id, r.in_tx_id FROM transfer_rejections r"
            " JOIN transactions t ON t.id = r.out_tx_id"
            " JOIN accounts a ON a.id = t.account_id WHERE a.user_id=?",
            (uid,),
        )
    }


def candidates(
    c: sqlite3.Connection,
    uid: int,
    max_days: int = SUGGEST_DAYS,
) -> list[TransferCandidate]:
    """Handle candidates."""
    rows = [
        TransferMatchRow(
            id=row["id"],
            date=row["date"],
            amount=row["amount"],
            description=row["description"],
            account_id=row["account_id"],
            transfer_id=row["transfer_id"],
        )
        for row in c.execute(LINKABLE_COLUMNS, (uid,))
    ]
    return find_pairs(rows, max_days, rejections(c, uid))


def detect(
    c: sqlite3.Connection,
    uid: int,
    auto_days: int = AUTO_DAYS,
    max_days: int = SUGGEST_DAYS,
) -> tuple[list[MergedTransfer], list[TransferCandidate]]:
    """
    Scan the ledger and merge what is unambiguous. Pairs that landed on the same.

    day (or one apart, since banks post the legs at different times) are merged.
    outright; anything looser is handed back as a suggestion for the user.

    Returns ``(merged, suggestions)`` where ``merged`` carries the new transfer
    ids so the caller can offer an undo.
    """
    auto, suggested = split_confident(candidates(c, uid, max_days), auto_days)
    merged: list[MergedTransfer] = []
    for pair in auto:
        try:
            transfer_id = link(
                c,
                uid,
                LinkRequest(pair.out_tx_id, pair.in_tx_id, origin="matched"),
            )
        except LinkError:
            continue
        merged.append(
            MergedTransfer(
                id=transfer_id,
                out_tx_id=pair.out_tx_id,
                in_tx_id=pair.in_tx_id,
                amount=pair.amount,
                days=pair.days,
                hint=pair.hint,
                mismatch=pair.mismatch,
            ),
        )
    return merged, suggested
