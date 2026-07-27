"""
The database side of transfers: merging two transactions into one entity,
splitting them apart again, and running detection over a user's ledger.

Kept out of the router so the import and sync pipelines can merge freshly
ingested rows through exactly the same code path the UI uses.
"""

import sqlite3
import uuid
from datetime import UTC, datetime

from .transfer_match import AUTO_DAYS, SUGGEST_DAYS, find_pairs, split_confident

LINKABLE_COLUMNS = (
    "SELECT t.id, t.date, t.amount, t.currency, t.description, t.account_id, t.transfer_id"
    " FROM transactions t JOIN accounts a ON a.id = t.account_id"
    " WHERE a.user_id=? AND t.transfer_id IS NULL"
    # a reconcile adjustment is bookkeeping, not money moving between accounts
    # — matching one against a real row would merge fiction with fact
    " AND t.source != 'adjustment'"
)


def serialize_transfer(r):
    return {
        "id": r["id"],
        "outTxId": r["out_tx_id"],
        "inTxId": r["in_tx_id"],
        "origin": r["origin"],
        "note": r["note"],
        "createdAt": r["created_at"],
    }


def list_transfers(c, uid):
    return [
        serialize_transfer(r)
        for r in c.execute(
            "SELECT id, out_tx_id, in_tx_id, origin, note, created_at FROM transfers"
            " WHERE user_id=? ORDER BY created_at DESC, id",
            (uid,),
        )
    ]


def owned_tx(c, uid, tx_id):
    return c.execute(
        "SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id"
        " WHERE t.id=? AND a.user_id=?",
        (tx_id, uid),
    ).fetchone()


class LinkError(Exception):
    """
    Why a pair cannot become a transfer. The router turns it into a 400.
    """


def link(c, uid, out_tx_id, in_tx_id, origin="manual", note=""):
    """
    Merge two existing transactions into a transfer. The rows are left in place
    — only ``transfer_id`` is stamped and the categories are moved aside, so a
    later split restores exactly what was there.
    """
    out_row = owned_tx(c, uid, out_tx_id)
    in_row = owned_tx(c, uid, in_tx_id)
    if out_row is None or in_row is None:
        raise LinkError("unknown transaction")
    if out_row["amount"] >= 0 or in_row["amount"] <= 0:
        raise LinkError("a transfer needs one outflow and one inflow")
    if out_row["account_id"] == in_row["account_id"]:
        raise LinkError("both legs are on the same account")
    if out_row["transfer_id"] or in_row["transfer_id"]:
        raise LinkError("already part of a transfer")

    transfer_id = uuid.uuid4().hex
    # the checks above race with any other writer; the UNIQUE columns are what
    # actually enforce one transfer per transaction, so a loser here has to read
    # as a 400 "already linked" and not as a 500
    try:
        c.execute(
            "INSERT INTO transfers"
            " (id, user_id, out_tx_id, in_tx_id, origin, out_category_id, in_category_id,"
            "  note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                transfer_id,
                uid,
                out_tx_id,
                in_tx_id,
                origin,
                out_row["category_id"],
                in_row["category_id"],
                note,
                datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        )
    except sqlite3.IntegrityError as e:
        raise LinkError("already part of a transfer") from e
    c.execute(
        "UPDATE transactions SET transfer_id=?, category_id=NULL WHERE id IN (?, ?)",
        (transfer_id, out_tx_id, in_tx_id),
    )
    c.execute(
        "DELETE FROM transfer_rejections WHERE out_tx_id=? AND in_tx_id=?",
        (out_tx_id, in_tx_id),
    )
    return transfer_id


def split(c, uid, transfer_id):
    """
    Undo a merge: both transactions stay, get their categories back and stop
    pointing at the transfer. Returns False when the transfer is not the user's.
    """
    row = c.execute(
        "SELECT out_tx_id, in_tx_id, out_category_id, in_category_id FROM transfers"
        " WHERE id=? AND user_id=?",
        (transfer_id, uid),
    ).fetchone()
    if row is None:
        return False
    c.execute(
        "UPDATE transactions SET transfer_id=NULL, category_id=? WHERE id=?",
        (row["out_category_id"], row["out_tx_id"]),
    )
    c.execute(
        "UPDATE transactions SET transfer_id=NULL, category_id=? WHERE id=?",
        (row["in_category_id"], row["in_tx_id"]),
    )
    c.execute("DELETE FROM transfers WHERE id=?", (transfer_id,))
    return True


def detach_leg(c, uid, tx_id):
    """
    Split whatever transfer this transaction belongs to, so it can be deleted on
    its own. Without this the entity row cascades away while the surviving leg
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


def reject(c, uid, out_tx_id, in_tx_id):
    """
    Remember that this pair is not a transfer, so detection stops proposing it.
    """
    if owned_tx(c, uid, out_tx_id) is None or owned_tx(c, uid, in_tx_id) is None:
        raise LinkError("unknown transaction")
    c.execute(
        "INSERT OR IGNORE INTO transfer_rejections (out_tx_id, in_tx_id) VALUES (?, ?)",
        (out_tx_id, in_tx_id),
    )


def rejections(c, uid):
    return {
        (r["out_tx_id"], r["in_tx_id"])
        for r in c.execute(
            "SELECT r.out_tx_id, r.in_tx_id FROM transfer_rejections r"
            " JOIN transactions t ON t.id = r.out_tx_id"
            " JOIN accounts a ON a.id = t.account_id WHERE a.user_id=?",
            (uid,),
        )
    }


def candidates(c, uid, max_days=SUGGEST_DAYS):
    rows = list(c.execute(LINKABLE_COLUMNS, (uid,)))
    return find_pairs(rows, max_days=max_days, rejected=rejections(c, uid))


def detect(c, uid, auto_days=AUTO_DAYS, max_days=SUGGEST_DAYS):
    """
    Scan the ledger and merge what is unambiguous. Pairs that landed on the same
    day (or one apart, since banks post the legs at different times) are merged
    outright; anything looser is handed back as a suggestion for the user.

    Returns ``(merged, suggestions)`` where ``merged`` carries the new transfer
    ids so the caller can offer an undo.
    """
    auto, suggested = split_confident(candidates(c, uid, max_days), auto_days)
    merged = []
    for pair in auto:
        try:
            transfer_id = link(c, uid, pair["outTxId"], pair["inTxId"], origin="matched")
        except LinkError:
            continue
        merged.append({**pair, "id": transfer_id})
    return merged, suggested
