import json
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from ..auth import AuthenticatedUser, current_user
from ..db_records import TransactionRecord
from ..deps import TransactionResponse, conn, serialize_tx
from ..importer import tx_hash
from ..transfer_match import AUTO_DAYS, SUGGEST_DAYS, TransferCandidate, split_confident
from ..transfer_service import (
    LinkError,
    MergedTransfer,
    TransferResponse,
    candidates,
    detect,
    list_transfers,
    reject,
)
from ..transfer_service import link as link_pair
from ..transfer_service import split as split_transfer

router = APIRouter(prefix="/api/transfers", tags=["transfers"])

LEGS_BY_ID = (
    "SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id"
    " WHERE a.user_id=? AND t.id IN (SELECT value FROM json_each(?))"
)


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class TransferBody:
    fromAccountId: int
    toAccountId: int
    amount: int
    date: str
    comment: str = ""


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class PairBody:
    outTxId: int
    inTxId: int
    note: str = ""


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class TransfersResponse:
    rows: list[TransferResponse]


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class SuggestionsResponse:
    rows: list[TransferCandidate]
    transactions: list[TransactionResponse]


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class TransferIdResponse:
    transferId: str


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class DetectionResponse:
    merged: list[MergedTransfer]
    suggested: int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class OkResponse:
    ok: bool


def account_exists(c: sqlite3.Connection, account_id: int, uid: int) -> bool:
    return (
        c.execute("SELECT id FROM accounts WHERE id=? AND user_id=?", (account_id, uid)).fetchone()
        is not None
    )


@router.get("")
def get_transfers(user: Annotated[AuthenticatedUser, Depends(current_user)]) -> TransfersResponse:
    c = conn()
    try:
        return TransfersResponse(rows=list_transfers(c, user.id))
    finally:
        c.close()


@router.get("/suggestions")
def get_suggestions(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    maxDays: int = Query(default=SUGGEST_DAYS, ge=0, le=31),
) -> SuggestionsResponse:
    """
    Pairs that look like a transfer but that detection would not merge unasked
    — too far apart in time, or the two descriptions disagree. The transactions
    themselves ride along so the UI can show both sides without a second round
    trip.
    """
    uid = user.id
    c = conn()
    try:
        _, pairs = split_confident(candidates(c, uid, maxDays))
        ids = sorted({p.outTxId for p in pairs} | {p.inTxId for p in pairs})
        legs = (
            [
                serialize_tx(TransactionRecord.from_row(row))
                for row in c.execute(LEGS_BY_ID, (uid, json.dumps(ids)))
            ]
            if ids
            else []
        )
        return SuggestionsResponse(rows=pairs, transactions=legs)
    finally:
        c.close()


@router.post("")
def create_transfer(
    body: TransferBody, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> TransferIdResponse:
    """
    A transfer is two linked transactions: a negative row on the source account
    and a positive row on the destination, merged into one ``transfers`` entity.
    Both legs stay uncategorized, so they never count as income or expense.
    """
    uid = user.id
    if body.amount <= 0:
        raise HTTPException(422, "amount must be positive")
    if body.fromAccountId == body.toAccountId:
        raise HTTPException(400, "cannot transfer to the same account")
    c = conn()
    try:
        if not account_exists(c, body.fromAccountId, uid) or not account_exists(
            c, body.toAccountId, uid
        ):
            raise HTTPException(400, "unknown account")
        description = "Transfer"
        legs: list[int] = []
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
            if cur.lastrowid is None:
                raise RuntimeError("transaction insert did not return an id")
            legs.append(cur.lastrowid)
        transfer_id = link_pair(c, uid, legs[0], legs[1], note=body.comment)
        c.commit()
        return TransferIdResponse(transferId=transfer_id)
    except LinkError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        c.close()


@router.post("/link")
def link_transactions(
    body: PairBody, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> TransferIdResponse:
    """
    Merge a pair that is already in the ledger — the usual case for rows the
    bank sent us itself. Nothing is inserted or deleted: both transactions keep
    their id and hash, so the next sync still recognizes them.
    """
    c = conn()
    try:
        transfer_id = link_pair(
            c,
            user.id,
            body.outTxId,
            body.inTxId,
            note=body.note,
        )
        c.commit()
        return TransferIdResponse(transferId=transfer_id)
    except LinkError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        c.close()


@router.post("/suggestions/dismiss")
def dismiss_suggestion(
    body: PairBody, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> OkResponse:
    c = conn()
    try:
        reject(c, user.id, body.outTxId, body.inTxId)
        c.commit()
        return OkResponse(ok=True)
    except LinkError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        c.close()


@router.post("/detect")
def run_detection(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    maxDays: int = Query(default=SUGGEST_DAYS, ge=0, le=31),
) -> DetectionResponse:
    """
    Merge the pairs that are beyond doubt and report the rest as suggestions.
    """
    c = conn()
    try:
        merged, suggested = detect(c, user.id, AUTO_DAYS, maxDays)
        c.commit()
        return DetectionResponse(merged=merged, suggested=len(suggested))
    finally:
        c.close()


@router.delete("/{transfer_id}")
def delete_transfer(
    transfer_id: str, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> OkResponse:
    """
    Split a transfer back into two ordinary transactions, categories and all.
    The rows are never deleted here: half of them came from a bank, and deleting
    them would only invite the next sync to bring them back unlinked.
    """
    c = conn()
    try:
        if not split_transfer(c, user.id, str(transfer_id)):
            raise HTTPException(404, "transfer not found")
        c.commit()
        return OkResponse(ok=True)
    finally:
        c.close()
