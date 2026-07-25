import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import current_user
from ..deps import conn, serialize_tx
from ..importer import tx_hash
from ..transfer_match import AUTO_DAYS, SUGGEST_DAYS
from ..transfer_service import LinkError, candidates, detect, list_transfers, reject
from ..transfer_service import link as link_pair
from ..transfer_service import split as split_transfer

router = APIRouter(prefix="/api/transfers", tags=["transfers"])

LEGS_BY_ID = (
    "SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id"
    " WHERE a.user_id=? AND t.id IN (SELECT value FROM json_each(?))"
)


class TransferBody(BaseModel):
    fromAccountId: int
    toAccountId: int
    amount: int = Field(gt=0)
    date: str
    comment: str = ""


class PairBody(BaseModel):
    outTxId: int
    inTxId: int
    note: str = ""


def account_exists(c, account_id, uid):
    return (
        c.execute("SELECT id FROM accounts WHERE id=? AND user_id=?", (account_id, uid)).fetchone()
        is not None
    )


@router.get("")
def get_transfers(user: Annotated[dict, Depends(current_user)]):
    c = conn()
    try:
        return {"rows": list_transfers(c, user["id"])}
    finally:
        c.close()


@router.get("/suggestions")
def get_suggestions(
    user: Annotated[dict, Depends(current_user)],
    maxDays: int = Query(default=SUGGEST_DAYS, ge=0, le=31),
):
    """
    Pairs that look like a transfer but are not close enough in time to merge
    unasked. The transactions themselves ride along so the UI can show both
    sides without a second round trip.
    """
    uid = user["id"]
    c = conn()
    try:
        pairs = [p for p in candidates(c, uid, maxDays) if p["days"] > AUTO_DAYS]
        ids = sorted({p["outTxId"] for p in pairs} | {p["inTxId"] for p in pairs})
        legs = (
            [serialize_tx(r) for r in c.execute(LEGS_BY_ID, (uid, json.dumps(ids)))] if ids else []
        )
        return {"rows": pairs, "transactions": legs}
    finally:
        c.close()


@router.post("")
def create_transfer(body: TransferBody, user: Annotated[dict, Depends(current_user)]):
    """
    A transfer is two linked transactions: a negative row on the source account
    and a positive row on the destination, merged into one ``transfers`` entity.
    Both legs stay uncategorized, so they never count as income or expense.
    """
    uid = user["id"]
    if body.fromAccountId == body.toAccountId:
        raise HTTPException(400, "cannot transfer to the same account")
    c = conn()
    try:
        if not account_exists(c, body.fromAccountId, uid) or not account_exists(
            c, body.toAccountId, uid
        ):
            raise HTTPException(400, "unknown account")
        description = "Transfer"
        legs = []
        for account_id, amount in (
            (body.fromAccountId, -body.amount),
            (body.toAccountId, body.amount),
        ):
            cur = c.execute(
                """INSERT INTO transactions
                   (date, amount, description, account_id, comment, hash, source)
                   VALUES (?, ?, ?, ?, ?, ?, 'transfer')""",
                (
                    body.date,
                    amount,
                    description,
                    account_id,
                    body.comment,
                    tx_hash(account_id, body.date, amount, description),
                ),
            )
            legs.append(cur.lastrowid)
        transfer_id = link_pair(c, uid, legs[0], legs[1], note=body.comment)
        c.commit()
        return {"transferId": transfer_id}
    except LinkError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        c.close()


@router.post("/link")
def link_transactions(body: PairBody, user: Annotated[dict, Depends(current_user)]):
    """
    Merge a pair that is already in the ledger — the usual case for rows the
    bank sent us itself. Nothing is inserted or deleted: both transactions keep
    their id and hash, so the next sync still recognizes them.
    """
    c = conn()
    try:
        transfer_id = link_pair(c, user["id"], body.outTxId, body.inTxId, note=body.note)
        c.commit()
        return {"transferId": transfer_id}
    except LinkError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        c.close()


@router.post("/suggestions/dismiss")
def dismiss_suggestion(body: PairBody, user: Annotated[dict, Depends(current_user)]):
    c = conn()
    try:
        reject(c, user["id"], body.outTxId, body.inTxId)
        c.commit()
        return {"ok": True}
    except LinkError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        c.close()


@router.post("/detect")
def run_detection(
    user: Annotated[dict, Depends(current_user)],
    maxDays: int = Query(default=SUGGEST_DAYS, ge=0, le=31),
):
    """
    Merge the pairs that are beyond doubt and report the rest as suggestions.
    """
    c = conn()
    try:
        merged, suggested = detect(c, user["id"], AUTO_DAYS, maxDays)
        c.commit()
        return {"merged": merged, "suggested": len(suggested)}
    finally:
        c.close()


@router.delete("/{transfer_id}")
def delete_transfer(transfer_id: str, user: Annotated[dict, Depends(current_user)]):
    """
    Split a transfer back into two ordinary transactions, categories and all.
    The rows are never deleted here: half of them came from a bank, and deleting
    them would only invite the next sync to bring them back unlinked.
    """
    c = conn()
    try:
        if not split_transfer(c, user["id"], transfer_id):
            raise HTTPException(404, "transfer not found")
        c.commit()
        return {"ok": True}
    finally:
        c.close()
