# Copyright (c) 2026
"""Provide backend functionality."""

import re
import sqlite3
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass as pydantic_dataclass

from monori.server.app import db as dbmod
from monori.server.app.auth import AuthenticatedUser, current_user
from monori.server.app.db import begin_write
from monori.server.app.db_records import (
    CategorySignRecord,
    TransactionRecord,
    db_int,
    row_int,
    row_str,
)
from monori.server.app.deps import (
    IdResponse,
    SplitResponse,
    TransactionResponse,
    conn,
    serialize_transactions,
)
from monori.server.app.importer import tx_hash
from monori.server.app.transfer_service import detach_leg
from monori.server.app.value_types import Money, TransactionDate

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
MIN_SPLIT_PARTS = 2


_CONFIG = ConfigDict(extra="forbid", populate_by_name=True)


@pydantic_dataclass(config=_CONFIG)
class TxCreate:
    """Represent TxCreate."""

    date: TransactionDate
    amount: Money
    account_id: int = Field(alias="accountId")
    description: str = ""
    bank_category: str = Field(default="", alias="bankCategory")
    mcc: str = ""
    category_id: int | None = Field(default=None, alias="categoryId")
    comment: str = ""


@pydantic_dataclass(config=_CONFIG)
class TxPatch:
    """Represent TxPatch."""

    date: TransactionDate | None = None
    amount: Money | None = None
    account_id: int | None = Field(default=None, alias="accountId")
    description: str | None = None
    bank_category: str | None = Field(default=None, alias="bankCategory")
    mcc: str | None = None
    category_id: int | None = Field(default=None, alias="categoryId")
    comment: str | None = None
    hidden: bool | None = None


@pydantic_dataclass(config=_CONFIG)
class BulkBody:
    """Represent BulkBody."""

    action: str
    ids: list[int]
    category_id: int | None = Field(default=None, alias="categoryId")


@pydantic_dataclass(config=_CONFIG)
class SplitPart:
    """Represent SplitPart."""

    amount: Money
    category_id: int = Field(alias="categoryId")
    comment: str = ""


@pydantic_dataclass(config=_CONFIG)
class SplitBody:
    """Represent SplitBody."""

    parts: list[SplitPart]


@pydantic_dataclass(config=_CONFIG)
class RefundBody:
    """
    Represent a refund link request.
    """

    original_id: int = Field(alias="originalId")


@pydantic_dataclass(config=_CONFIG)
class TransactionListResponse:
    """Represent TransactionListResponse."""

    total: int
    rows: list[TransactionResponse]


@pydantic_dataclass(config=_CONFIG)
class TransactionListFilters:
    """Represent query parameters for the transaction list."""

    from_: Annotated[str | None, Query(alias="from")] = None
    to: str | None = None
    category_id: Annotated[int | None, Query(alias="categoryId")] = None
    account_id: Annotated[int | None, Query(alias="accountId")] = None
    uncategorized: bool = False
    hidden: bool = False
    q: str | None = None
    limit: Annotated[int, Query(ge=1, le=1000)] = 100
    offset: Annotated[int, Query(ge=0)] = 0


@pydantic_dataclass(config=_CONFIG)
class OkResponse:
    """Represent OkResponse."""

    ok: bool


@pydantic_dataclass(config=_CONFIG)
class SplitsResponse:
    """Represent SplitsResponse."""

    splits: list[SplitResponse]


@pydantic_dataclass(config=_CONFIG)
class BulkResponse:
    """Represent BulkResponse."""

    affected: int


@pydantic_dataclass(config=_CONFIG)
class RefundLinkResponse:
    """
    Represent a linked refund.
    """

    ok: bool
    refund_of_id: int = Field(serialization_alias="refundOfId")
    category_id: int | None = Field(serialization_alias="categoryId")


@pydantic_dataclass(config=_CONFIG)
class RefundUnlinkResponse:
    """
    Represent an unlinked refund.
    """

    ok: bool
    category_id: int | None = Field(serialization_alias="categoryId")


@pydantic_dataclass(config=_CONFIG)
class RefundSuggestionsResponse:
    """
    Represent candidate purchases for a refund.
    """

    rows: list[TransactionResponse]


def _validate_category_type(transaction_sign: int, amount: int, *, is_refund: bool = False) -> None:
    if amount < 0 and transaction_sign != -1:
        raise HTTPException(400, "expense transaction requires an expense category")
    if amount > 0 and is_refund and transaction_sign != -1:
        raise HTTPException(400, "linked refund requires an expense category")


def _resolve_category(
    c: dbmod.DatabaseConnection,
    category_id: int | None,
    uid: int,
    amount: int | None = None,
    *,
    is_refund: bool = False,
) -> int | None:
    """0 (or None handled by caller) means uncategorized; else must exist."""
    if category_id in (None, 0):
        return None
    category = c.execute(
        "SELECT c.id, t.transaction_sign FROM categories c"
        " JOIN category_groups g ON g.id = c.group_id"
        " JOIN category_group_types t ON t.id=g.type_id"
        " WHERE c.id=? AND g.user_id=?",
        (category_id, uid),
    ).fetchone()
    if not category:
        raise HTTPException(400, "unknown category")
    if amount is not None:
        _validate_category_type(
            CategorySignRecord.from_row(category).transaction_sign,
            amount,
            is_refund=is_refund,
        )
    return category_id


def _owned_transaction(c: sqlite3.Connection, tx_id: int, uid: int) -> TransactionRecord | None:
    row = c.execute(
        "SELECT t.* FROM transactions t JOIN accounts a ON a.id=t.account_id"
        " WHERE t.id=? AND a.user_id=?",
        (tx_id, uid),
    ).fetchone()
    return None if row is None else TransactionRecord.from_row(row)


def _refund_total(c: sqlite3.Connection, original_id: int, excluding: int | None = None) -> int:
    return int(
        c.execute(
            "SELECT COALESCE(SUM(t.amount), 0) FROM refund_links r"
            " JOIN transactions t ON t.id=r.refund_tx_id"
            " WHERE r.original_tx_id=? AND (? IS NULL OR r.refund_tx_id<>?)",
            (original_id, excluding, excluding),
        ).fetchone()[0]
    )


def _merchant_key(value: str) -> str:
    """
    Normalize merchant text like the frontend refund matcher.
    """
    letters = "a-z\u0430-\u044f\u0451"
    refund_words = "refund|return|\u0432\u043e\u0437\u0432\u0440\u0430\u0442"
    value = re.sub(rf"(?<![{letters}])({refund_words})(?![{letters}])", " ", value.lower())
    return " ".join(re.findall(rf"[{letters}]+", value))


def _validate_refund_amount(
    c: sqlite3.Connection,
    transaction: TransactionRecord,
    amount: int,
    uid: int,
) -> bool:
    link = c.execute(
        "SELECT original_tx_id FROM refund_links WHERE refund_tx_id=?",
        (transaction.id,),
    ).fetchone()
    if link is not None:
        if amount <= 0:
            raise HTTPException(400, "a linked refund must remain positive")
        original = cast(
            "TransactionRecord",
            _owned_transaction(c, int(link["original_tx_id"]), uid),
        )
        if _refund_total(c, original.id, transaction.id) + amount > -original.amount:
            raise HTTPException(400, "refunds cannot exceed the original purchase")
    linked_total = _refund_total(c, transaction.id)
    if linked_total and (amount >= 0 or linked_total > -amount):
        raise HTTPException(400, "purchase amount cannot be less than its refunds")
    return link is not None


def _edited_category(
    c: sqlite3.Connection,
    patch: TxPatch,
    transaction: TransactionRecord,
    amount: int,
    uid: int,
) -> int | None:
    is_refund = (
        c.execute("SELECT 1 FROM refund_links WHERE refund_tx_id=?", (transaction.id,)).fetchone()
        is not None
    )
    category = transaction.category_id
    if patch.category_id is not None:
        if c.execute("SELECT 1 FROM splits WHERE transaction_id=?", (transaction.id,)).fetchone():
            raise HTTPException(400, "remove the split before categorizing the parent")
        category = _resolve_category(c, patch.category_id, uid, amount, is_refund=is_refund)
        if is_refund:
            original_category = c.execute(
                "SELECT t.category_id FROM refund_links r"
                " JOIN transactions t ON t.id=r.original_tx_id WHERE r.refund_tx_id=?",
                (transaction.id,),
            ).fetchone()[0]
            if category != original_category:
                raise HTTPException(400, "refund category must match the original purchase")
    elif patch.amount is not None and category is not None:
        _resolve_category(c, category, uid, amount, is_refund=is_refund)
    return category


def _resolve_account(c: dbmod.DatabaseConnection, account_id: int, uid: int) -> int:
    if not c.execute(
        "SELECT id FROM accounts WHERE id=? AND user_id=?",
        (account_id, uid),
    ).fetchone():
        raise HTTPException(400, "unknown account")
    return account_id


@router.get("")
def list_transactions(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    filters: Annotated[TransactionListFilters, Depends()],
) -> TransactionListResponse:
    """Handle list transactions."""
    uid = user.id
    params = {
        "uid": uid,
        "from": filters.from_,
        "to": filters.to,
        "uncat": 1 if filters.uncategorized else 0,
        "hidden": 1 if filters.hidden else 0,
        "cat": filters.category_id,
        "acct": filters.account_id,
        "q": f"%{filters.q.lower()}%" if filters.q else None,
        "limit": filters.limit,
        "offset": filters.offset,
    }
    c = conn()
    try:
        where = """
            FROM transactions
            WHERE account_id IN (SELECT id FROM accounts WHERE user_id=:uid)
              AND hidden = :hidden
              AND (:from IS NULL OR date(date) >= date(:from))
              AND (:to IS NULL OR date(date) <= date(:to))
              AND (:uncat = 0 OR (category_id IS NULL AND NOT EXISTS (
                    SELECT 1 FROM splits s WHERE s.transaction_id=transactions.id
                  )))
              AND (:uncat = 1 OR :cat IS NULL OR category_id = :cat OR EXISTS (
                    SELECT 1 FROM splits s
                    WHERE s.transaction_id=transactions.id AND s.category_id=:cat
                  ))
              AND (:acct IS NULL OR account_id = :acct)
              AND (:q IS NULL OR LOWER(description) LIKE :q)
        """
        count_row = c.execute("SELECT COUNT(*)" + where, params).fetchone()
        if count_row is None:
            msg = "transaction count query returned no row"
            raise RuntimeError(msg)
        total = db_int(count_row[0], "transaction count")
        rows = c.execute(
            "SELECT *" + where + " ORDER BY date DESC, id DESC LIMIT :limit OFFSET :offset",
            params,
        )
        cursor = c.cursor()
        return TransactionListResponse(total=total, rows=serialize_transactions(cursor, rows))
    finally:
        c.close()


@router.post("")
def create_transaction(
    body: TxCreate,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> IdResponse:
    """Handle create transaction."""
    uid = user.id
    c = conn()
    try:
        category = _resolve_category(c, body.category_id, uid, body.amount)
        account = _resolve_account(c, body.account_id, uid)
        cur = c.execute(
            """INSERT INTO transactions
               (date, amount, description, bank_category, mcc, category_id, account_id,
                comment, hash, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual')""",
            (
                body.date,
                body.amount,
                body.description,
                body.bank_category,
                body.mcc,
                category,
                account,
                body.comment,
                tx_hash(account, body.date, body.amount, body.description),
            ),
        )
        c.commit()
        return IdResponse(id=cur.lastrowid)
    finally:
        c.close()


@router.patch("/{tx_id}")
def patch_transaction(
    tx_id: int,
    patch: TxPatch,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> OkResponse:
    """Handle patch transaction."""
    uid = user.id
    c = conn()
    try:
        begin_write(c)
        row = c.execute(
            "SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id"
            " WHERE t.id=? AND a.user_id=?",
            (tx_id, uid),
        ).fetchone()
        if not row:
            raise HTTPException(404, "transaction not found")
        transaction = TransactionRecord.from_row(row)
        date = patch.date if patch.date is not None else transaction.date
        amount = patch.amount if patch.amount is not None else transaction.amount
        is_refund = _validate_refund_amount(c, transaction, amount, uid)
        split_row = c.execute(
            "SELECT SUM(amount) FROM splits WHERE transaction_id=?",
            (tx_id,),
        ).fetchone()
        if split_row is None:
            msg = "split total query returned no row"
            raise RuntimeError(msg)
        split_value = split_row[0]
        split_total = None if split_value is None else db_int(split_value, "split total")
        if split_total is not None and amount != split_total:
            raise HTTPException(400, "edit the split parts before changing the total amount")
        description = (
            patch.description if patch.description is not None else transaction.description
        )
        bank_category = (
            patch.bank_category if patch.bank_category is not None else transaction.bank_category
        )
        mcc = patch.mcc if patch.mcc is not None else transaction.mcc
        comment = patch.comment if patch.comment is not None else transaction.comment
        category = _edited_category(
            c,
            patch,
            transaction,
            amount,
            uid,
        )
        account = transaction.account_id
        if patch.account_id is not None:
            account = _resolve_account(c, patch.account_id, uid)
        hidden = int(patch.hidden) if patch.hidden is not None else int(transaction.hidden)
        c.execute(
            """UPDATE transactions
               SET date=?, amount=?, description=?, bank_category=?, mcc=?, category_id=?,
                   account_id=?, comment=?, hidden=?, hash=?
               WHERE id=?""",
            (
                date,
                amount,
                description,
                bank_category,
                mcc,
                category,
                account,
                comment,
                hidden,
                tx_hash(account, date, amount, description),
                tx_id,
            ),
        )
        if not is_refund and category != transaction.category_id:
            c.execute(
                "UPDATE transactions SET category_id=? WHERE id IN"
                " (SELECT refund_tx_id FROM refund_links WHERE original_tx_id=?)",
                (category, tx_id),
            )
        c.commit()
        return OkResponse(ok=True)
    finally:
        c.close()


@router.get("/{refund_tx_id}/refund-suggestions")
def refund_suggestions(
    refund_tx_id: int,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> RefundSuggestionsResponse:
    """
    Suggest purchases that a positive transaction can refund.
    """
    uid = user.id
    c = conn()
    try:
        refund = _owned_transaction(c, refund_tx_id, uid)
        if refund is None:
            raise HTTPException(404, "transaction not found")
        if refund.amount <= 0:
            raise HTTPException(400, "only a positive transaction can be a refund")
        if refund.transfer_id is not None:
            raise HTTPException(400, "transfer transactions cannot be refunds")
        if c.execute(
            "SELECT 1 FROM splits WHERE transaction_id=? LIMIT 1",
            (refund_tx_id,),
        ).fetchone():
            raise HTTPException(400, "split transactions cannot be refunds")
        key = _merchant_key(refund.description)
        current = c.execute(
            "SELECT original_tx_id FROM refund_links WHERE refund_tx_id=?",
            (refund_tx_id,),
        ).fetchone()
        current_id = int(current["original_tx_id"]) if current is not None else None
        rows = c.execute(
            "SELECT t.*, COALESCE((SELECT SUM(rt.amount) FROM refund_links rl"
            " JOIN transactions rt ON rt.id=rl.refund_tx_id"
            " WHERE rl.original_tx_id=t.id AND rl.refund_tx_id<>?), 0) AS used_refund"
            " FROM transactions t JOIN accounts a ON a.id=t.account_id"
            " WHERE a.user_id=? AND t.amount<0 AND t.date<=? AND t.transfer_id IS NULL"
            " AND t.id<>? AND NOT EXISTS (SELECT 1 FROM splits s WHERE s.transaction_id=t.id)"
            " ORDER BY t.date DESC, t.id DESC",
            (refund_tx_id, uid, refund.date, refund_tx_id),
        ).fetchall()
        candidates: list[tuple[bool, sqlite3.Row]] = []
        for row in rows:
            if -int(row["amount"]) - int(row["used_refund"]) < refund.amount:
                continue
            same_merchant = bool(key) and _merchant_key(str(row["description"])) == key
            if row["id"] != current_id and not same_merchant and -row["amount"] != refund.amount:
                continue
            candidates.append((not same_merchant, row))
        candidates.sort(key=lambda item: item[0])
        selected = [row for _, row in candidates[:20]]
        return RefundSuggestionsResponse(rows=serialize_transactions(c.cursor(), selected))
    finally:
        c.close()


@router.put("/{refund_tx_id}/refund")
def link_refund(
    refund_tx_id: int,
    body: RefundBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> RefundLinkResponse:
    """
    Link a positive transaction to its original purchase.
    """
    uid = user.id
    c = conn()
    try:
        begin_write(c)
        refund = _owned_transaction(c, refund_tx_id, uid)
        original = _owned_transaction(c, body.original_id, uid)
        if refund is None or original is None:
            raise HTTPException(404, "transaction not found")
        if refund.amount <= 0 or original.amount >= 0:
            raise HTTPException(400, "a refund must link a positive transaction to a purchase")
        if original.date > refund.date:
            raise HTTPException(400, "a refund cannot predate its original purchase")
        if refund.transfer_id is not None or original.transfer_id is not None:
            raise HTTPException(400, "transfer transactions cannot be refunds")
        if c.execute(
            "SELECT 1 FROM splits WHERE transaction_id IN (?, ?) LIMIT 1",
            (refund_tx_id, body.original_id),
        ).fetchone():
            raise HTTPException(400, "split transactions cannot be refunds")
        if original.category_id is not None:
            _resolve_category(c, original.category_id, uid, original.amount)
        if _refund_total(c, body.original_id, refund_tx_id) + refund.amount > -original.amount:
            raise HTTPException(400, "refunds cannot exceed the original purchase")
        c.execute(
            "INSERT INTO refund_links (refund_tx_id, original_tx_id) VALUES (?, ?)"
            " ON CONFLICT(refund_tx_id) DO UPDATE SET original_tx_id=excluded.original_tx_id",
            (refund_tx_id, body.original_id),
        )
        c.execute(
            "UPDATE transactions SET category_id=? WHERE id=?",
            (original.category_id, refund_tx_id),
        )
        c.commit()
        return RefundLinkResponse(
            ok=True,
            refund_of_id=body.original_id,
            category_id=original.category_id,
        )
    finally:
        c.close()


@router.delete("/{refund_tx_id}/refund")
def unlink_refund(
    refund_tx_id: int,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> RefundUnlinkResponse:
    """
    Remove a refund link while preserving its category.
    """
    uid = user.id
    c = conn()
    try:
        begin_write(c)
        refund = _owned_transaction(c, refund_tx_id, uid)
        if refund is None:
            raise HTTPException(404, "transaction not found")
        deleted = c.execute(
            "DELETE FROM refund_links WHERE refund_tx_id=?",
            (refund_tx_id,),
        ).rowcount
        if not deleted:
            raise HTTPException(404, "refund link not found")
        c.commit()
        return RefundUnlinkResponse(ok=True, category_id=refund.category_id)
    finally:
        c.close()


@router.put("/{tx_id}/splits")
def replace_splits(
    tx_id: int,
    body: SplitBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SplitsResponse:
    """Atomically replace every categorized part, or clear the split with an empty list."""
    uid = user.id
    c = conn()
    try:
        begin_write(c)
        transaction = _split_parent(c, tx_id, uid)
        _validate_split_parts(c, transaction, body.parts, uid)
        _replace_split_rows(c, tx_id, body.parts)
        c.commit()
        return SplitsResponse(splits=_serialized_splits(c, tx_id))
    finally:
        c.close()


def _split_parent(c: dbmod.DatabaseConnection, tx_id: int, uid: int) -> TransactionRecord:
    row = c.execute(
        "SELECT t.* FROM transactions t JOIN accounts a ON a.id=t.account_id"
        " WHERE t.id=? AND a.user_id=?",
        (tx_id, uid),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "transaction not found")
    transaction = TransactionRecord.from_row(row)
    if transaction.transfer_id is not None:
        raise HTTPException(400, "transfer transactions cannot be split")
    return transaction


def _validate_split_parts(
    c: dbmod.DatabaseConnection,
    transaction: TransactionRecord,
    parts: list[SplitPart],
    uid: int,
) -> None:
    if not parts:
        return
    if c.execute(
        "SELECT 1 FROM refund_links WHERE refund_tx_id=? OR original_tx_id=? LIMIT 1",
        (transaction.id, transaction.id),
    ).fetchone():
        raise HTTPException(400, "refund transactions cannot be split")
    if len(parts) < MIN_SPLIT_PARTS:
        raise HTTPException(400, "a split requires at least two parts")
    if any(part.amount == 0 for part in parts):
        raise HTTPException(400, "split amounts cannot be zero")
    if any((part.amount > 0) != (transaction.amount > 0) for part in parts):
        raise HTTPException(400, "split parts must have the transaction's sign")
    if sum(part.amount for part in parts) != transaction.amount:
        raise HTTPException(400, "split amounts must equal the transaction amount")
    for part in parts:
        _resolve_category(c, part.category_id, uid, part.amount)


def _replace_split_rows(c: dbmod.DatabaseConnection, tx_id: int, parts: list[SplitPart]) -> None:
    c.execute("DELETE FROM splits WHERE transaction_id=?", (tx_id,))
    for sort, part in enumerate(parts):
        c.execute(
            "INSERT INTO splits"
            " (transaction_id, category_id, amount, comment, sort) VALUES (?, ?, ?, ?, ?)",
            (tx_id, part.category_id, part.amount, part.comment, sort),
        )
    if parts:
        c.execute("UPDATE transactions SET category_id=NULL WHERE id=?", (tx_id,))


def _serialized_splits(c: dbmod.DatabaseConnection, tx_id: int) -> list[SplitResponse]:
    rows = c.execute(
        "SELECT id, category_id, amount, comment FROM splits"
        " WHERE transaction_id=? ORDER BY sort, id",
        (tx_id,),
    )
    return [
        SplitResponse(
            id=row_int(row, "id"),
            category_id=row_int(row, "category_id"),
            amount=row_int(row, "amount"),
            comment=row_str(row, "comment"),
        )
        for row in rows
    ]


@router.delete("/{tx_id}")
def delete_transaction(
    tx_id: int,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> OkResponse:
    """Handle delete transaction."""
    uid = user.id
    c = conn()
    try:
        detach_leg(c, uid, tx_id)
        cur = c.execute(
            "DELETE FROM transactions WHERE id=?"
            " AND account_id IN (SELECT id FROM accounts WHERE user_id=?)",
            (tx_id, uid),
        )
        c.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "transaction not found")
        return OkResponse(ok=True)
    finally:
        c.close()


@router.post("/bulk")
def bulk_transactions(
    body: BulkBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> BulkResponse:
    """Handle bulk transactions."""
    uid = user.id
    if body.action not in ("categorize", "move", "delete"):
        raise HTTPException(400, "action must be 'categorize', 'move' or 'delete'")
    c = conn()
    try:
        begin_write(c)
        affected = 0
        if body.action == "delete":
            for tx_id in body.ids:
                detach_leg(c, uid, tx_id)
                affected += c.execute(
                    "DELETE FROM transactions WHERE id=?"
                    " AND account_id IN (SELECT id FROM accounts WHERE user_id=?)",
                    (tx_id, uid),
                ).rowcount
        else:
            category = _resolve_category(c, body.category_id, uid)

            for tx_id in body.ids:
                row = c.execute(
                    "SELECT t.amount, (SELECT COUNT(*) FROM splits s"
                    " WHERE s.transaction_id=t.id) AS is_split"
                    ", EXISTS(SELECT 1 FROM refund_links r"
                    " WHERE r.refund_tx_id=t.id) AS is_refund"
                    " FROM transactions t JOIN accounts a ON a.id = t.account_id"
                    " WHERE t.id=? AND a.user_id=?",
                    (tx_id, uid),
                ).fetchone()
                if row is not None and db_int(row["is_split"], "is_split"):
                    raise HTTPException(400, "remove the split before categorizing the parent")
                if row is not None and category is not None:
                    _resolve_category(
                        c,
                        category,
                        uid,
                        row_int(row, "amount"),
                        is_refund=bool(row["is_refund"]),
                    )
            for tx_id in body.ids:
                affected += c.execute(
                    "UPDATE transactions SET category_id=? WHERE id=?"
                    " AND account_id IN (SELECT id FROM accounts WHERE user_id=?)",
                    (category, tx_id, uid),
                ).rowcount
        c.commit()
        return BulkResponse(affected=affected)
    finally:
        c.close()
