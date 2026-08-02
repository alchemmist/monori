"""Provide backend functionality."""

import json
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass as pydantic_dataclass

from app.auth import AuthenticatedUser, current_user
from app.db_records import TransactionRecord
from app.deps import TransactionResponse, conn, serialize_tx
from app.importer import tx_hash
from app.transfer_match import AUTO_DAYS, SUGGEST_DAYS, split_confident
from app.transfer_service import (
    LinkError,
    MergedTransfer,
    TransferResponse,
    candidates,
    detect,
    list_transfers,
    reject,
)
from app.transfer_service import link as link_pair
from app.transfer_service import split as split_transfer

router = APIRouter(prefix="/api/transfers", tags=["transfers"])

LEGS_BY_ID = (
    "SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id"
    " WHERE a.user_id=? AND t.id IN (SELECT value FROM json_each(?))"
)


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class TransferBody:
    """Represent TransferBody."""

    amount: int
    date: str
    from_account_id: int = Field(alias="fromAccountId")
    to_account_id: int = Field(alias="toAccountId")
    comment: str = ""


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class PairBody:
    """Represent PairBody."""

    out_tx_id: int = Field(alias="outTxId")
    in_tx_id: int = Field(alias="inTxId")
    note: str = ""


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class TransfersResponse:
    """Represent TransfersResponse."""

    rows: list[TransferResponse]


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class SuggestionsResponse:
    """Represent SuggestionsResponse."""

    rows: list["SuggestionResponse"]
    transactions: list[TransactionResponse]


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class SuggestionResponse:
    """Represent SuggestionResponse."""

    amount: int
    days: int
    hint: bool
    mismatch: bool
    out_tx_id: int = Field(serialization_alias="outTxId")
    in_tx_id: int = Field(serialization_alias="inTxId")


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class TransferIdResponse:
    """Represent TransferIdResponse."""

    transfer_id: str = Field(serialization_alias="transferId")


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class DetectionResponse:
    """Represent DetectionResponse."""

    merged: list[MergedTransfer]
    suggested: int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class OkResponse:
    """Represent OkResponse."""

    ok: bool


def account_exists(c: sqlite3.Connection, account_id: int, uid: int) -> bool:
    """Handle account exists."""
    return (
        c.execute("SELECT id FROM accounts WHERE id=? AND user_id=?", (account_id, uid)).fetchone()
        is not None
    )


@router.get("")
def get_transfers(user: Annotated[AuthenticatedUser, Depends(current_user)]) -> TransfersResponse:
    """Handle get transfers."""
    c = conn()
    try:
        return TransfersResponse(rows=list_transfers(c, user.id))
    finally:
        c.close()


@router.get("/suggestions")
def get_suggestions(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    max_days: Annotated[int, Query(ge=0, le=31, alias="maxDays")] = SUGGEST_DAYS,
) -> SuggestionsResponse:
    """
    Pairs that look like a transfer but that detection would not merge unasked.

    — too far apart in time, or the two descriptions disagree. The transactions.
    themselves ride along so the UI can show both sides without a second round
    trip.
    """
    uid = user.id
    c = conn()
    try:
        _, pairs = split_confident(candidates(c, uid, max_days))
        ids = sorted({p.out_tx_id for p in pairs} | {p.in_tx_id for p in pairs})
        legs = (
            [
                serialize_tx(TransactionRecord.from_row(row))
                for row in c.execute(LEGS_BY_ID, (uid, json.dumps(ids)))
            ]
            if ids
            else []
        )
        return SuggestionsResponse(
            rows=[
                SuggestionResponse(
                    out_tx_id=pair.out_tx_id,
                    in_tx_id=pair.in_tx_id,
                    amount=pair.amount,
                    days=pair.days,
                    hint=pair.hint,
                    mismatch=pair.mismatch,
                )
                for pair in pairs
            ],
            transactions=legs,
        )
    finally:
        c.close()


@router.post("")
def create_transfer(
    body: TransferBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> TransferIdResponse:
    """
    Handle A transfer is two linked transactions: a negative row on the source account.

    and a positive row on the destination, merged into one ``transfers`` entity.
    Both legs stay uncategorized, so they never count as income or expense.
    """
    uid = user.id
    if body.amount <= 0:
        raise HTTPException(422, "amount must be positive")
    if body.from_account_id == body.to_account_id:
        raise HTTPException(400, "cannot transfer to the same account")
    c = conn()
    try:
        if not account_exists(c, body.from_account_id, uid) or not account_exists(
            c,
            body.to_account_id,
            uid,
        ):
            raise HTTPException(400, "unknown account")
        description = "Transfer"
        legs: list[int] = []
        for account_id, amount in (
            (body.from_account_id, -body.amount),
            (body.to_account_id, body.amount),
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
                msg = "transaction insert did not return an id"
                raise RuntimeError(msg)
            legs.append(cur.lastrowid)
        transfer_id = link_pair(c, uid, legs[0], legs[1], note=body.comment)
        c.commit()
        return TransferIdResponse(transfer_id=transfer_id)
    except LinkError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        c.close()


@router.post("/link")
def link_transactions(
    body: PairBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> TransferIdResponse:
    """
    Merge a pair that is already in the ledger — the usual case for rows the.

    bank sent us itself. Nothing is inserted or deleted: both transactions keep.
    their id and hash, so the next sync still recognizes them.
    """
    c = conn()
    try:
        transfer_id = link_pair(
            c,
            user.id,
            body.out_tx_id,
            body.in_tx_id,
            note=body.note,
        )
        c.commit()
        return TransferIdResponse(transfer_id=transfer_id)
    except LinkError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        c.close()


@router.post("/suggestions/dismiss")
def dismiss_suggestion(
    body: PairBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> OkResponse:
    """Handle dismiss suggestion."""
    c = conn()
    try:
        reject(c, user.id, body.out_tx_id, body.in_tx_id)
        c.commit()
        return OkResponse(ok=True)
    except LinkError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        c.close()


@router.post("/detect")
def run_detection(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    max_days: Annotated[int, Query(ge=0, le=31, alias="maxDays")] = SUGGEST_DAYS,
) -> DetectionResponse:
    """Merge the pairs that are beyond doubt and report the rest as suggestions."""
    c = conn()
    try:
        merged, suggested = detect(c, user.id, AUTO_DAYS, max_days)
        c.commit()
        return DetectionResponse(merged=merged, suggested=len(suggested))
    finally:
        c.close()


@router.delete("/{transfer_id}")
def delete_transfer(
    transfer_id: str,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
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
