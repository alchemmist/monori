import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import current_user
from ..deps import conn
from ..importer import tx_hash

router = APIRouter(prefix="/api/transfers", tags=["transfers"])


class TransferBody(BaseModel):
    fromAccountId: int
    toAccountId: int
    amount: int = Field(gt=0)
    date: str
    comment: str = ""


def _account_exists(c, account_id, uid):
    return (
        c.execute("SELECT id FROM accounts WHERE id=? AND user_id=?", (account_id, uid)).fetchone()
        is not None
    )


@router.post("")
def create_transfer(body: TransferBody, user: Annotated[dict, Depends(current_user)]):
    """A transfer is two linked transactions sharing a transfer_id: a negative
    row on the source account and a positive row on the destination. Both are
    uncategorized, so they never count as income or expense."""
    uid = user["id"]
    if body.fromAccountId == body.toAccountId:
        raise HTTPException(400, "cannot transfer to the same account")
    c = conn()
    try:
        if not _account_exists(c, body.fromAccountId, uid) or not _account_exists(
            c, body.toAccountId, uid
        ):
            raise HTTPException(400, "unknown account")
        transfer_id = uuid.uuid4().hex
        description = "Transfer"
        for account_id, amount in (
            (body.fromAccountId, -body.amount),
            (body.toAccountId, body.amount),
        ):
            c.execute(
                """INSERT INTO transactions
                   (date, amount, description, account_id, transfer_id, comment, hash, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'transfer')""",
                (
                    body.date,
                    amount,
                    description,
                    account_id,
                    transfer_id,
                    body.comment,
                    tx_hash(body.date, amount, description),
                ),
            )
        c.commit()
        return {"transferId": transfer_id}
    finally:
        c.close()


@router.delete("/{transfer_id}")
def delete_transfer(transfer_id: str, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        cur = c.execute(
            "DELETE FROM transactions WHERE transfer_id=?"
            " AND account_id IN (SELECT id FROM accounts WHERE user_id=?)",
            (transfer_id, uid),
        )
        c.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "transfer not found")
        return {"ok": True}
    finally:
        c.close()
