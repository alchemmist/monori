import sqlite3
from collections.abc import Mapping
from typing import Annotated, NotRequired, TypedDict, cast

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import current_user
from ..db import begin_write
from ..deps import conn, serialize_transactions
from ..importer import tx_hash
from ..transfer_service import detach_leg

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


class TxCreate(TypedDict):
    date: str
    amount: int
    accountId: int
    description: NotRequired[str]
    bankCategory: NotRequired[str]
    mcc: NotRequired[str]
    categoryId: NotRequired[int | None]
    comment: NotRequired[str]


class TxPatch(TypedDict, total=False):
    date: str | None
    amount: int | None
    accountId: int | None
    description: str | None
    bankCategory: str | None
    mcc: str | None
    categoryId: int | None
    comment: str | None
    hidden: bool | None


class BulkBody(TypedDict):
    action: str
    ids: list[int]
    categoryId: NotRequired[int | None]


class SplitPart(TypedDict):
    categoryId: int
    amount: int
    comment: NotRequired[str]


class SplitBody(TypedDict):
    parts: list[SplitPart]


class TxRow(TypedDict):
    id: int
    date: str
    amount: int
    description: str
    bank_category: str
    mcc: str
    category_id: int | None
    account_id: int
    transfer_id: int | None
    comment: str
    hidden: int


def _validate_category_type(transaction_sign: int, amount: int) -> None:
    if amount < 0 and transaction_sign != -1:
        raise HTTPException(400, "expense transaction requires an expense category")
    if amount > 0 and transaction_sign != 1:
        raise HTTPException(400, "income transaction requires an income category")


def _resolve_category(
    c: sqlite3.Connection,
    category_id: int | None,
    uid: int,
    amount: int | None = None,
) -> int | None:
    """
    0 (or None handled by caller) means uncategorized; else must exist.
    """
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
        _validate_category_type(cast(int, category["transaction_sign"]), amount)
    return category_id


def _resolve_account(c: sqlite3.Connection, account_id: int, uid: int) -> int:
    if not c.execute(
        "SELECT id FROM accounts WHERE id=? AND user_id=?", (account_id, uid)
    ).fetchone():
        raise HTTPException(400, "unknown account")
    return account_id


@router.get("")
def list_transactions(
    user: Annotated[dict[str, object], Depends(current_user)],
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    categoryId: int | None = None,
    accountId: int | None = None,
    uncategorized: bool = False,
    hidden: bool = False,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    uid = cast(int, user["id"])
    params = {
        "uid": uid,
        "from": from_,
        "to": to,
        "uncat": 1 if uncategorized else 0,
        "hidden": 1 if hidden else 0,
        "cat": categoryId,
        "acct": accountId,
        "q": f"%{q.lower()}%" if q else None,
        "limit": limit,
        "offset": offset,
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
        total = c.execute("SELECT COUNT(*)" + where, params).fetchone()[0]
        rows = c.execute(
            "SELECT *" + where + " ORDER BY date DESC, id DESC LIMIT :limit OFFSET :offset",
            params,
        )
        return {"total": cast(int, total), "rows": serialize_transactions(c.cursor(), rows)}
    finally:
        c.close()


@router.post("")
def create_transaction(
    body: TxCreate, user: Annotated[dict[str, object], Depends(current_user)]
) -> dict[str, int]:
    uid = cast(int, user["id"])
    c = conn()
    try:
        category = _resolve_category(c, body.get("categoryId"), uid, body["amount"])
        account = _resolve_account(c, body["accountId"], uid)
        cur = c.execute(
            """INSERT INTO transactions
               (date, amount, description, bank_category, mcc, category_id, account_id,
                comment, hash, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual')""",
            (
                body["date"],
                body["amount"],
                body.get("description", ""),
                body.get("bankCategory", ""),
                body.get("mcc", ""),
                category,
                account,
                body.get("comment", ""),
                tx_hash(account, body["date"], body["amount"], body.get("description", "")),
            ),
        )
        c.commit()
        return {"id": cast(int, cur.lastrowid)}
    finally:
        c.close()


@router.patch("/{tx_id}")
def patch_transaction(
    tx_id: int, patch: TxPatch, user: Annotated[dict[str, object], Depends(current_user)]
) -> dict[str, bool]:
    uid = cast(int, user["id"])
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
        typed_row = cast(TxRow, row)
        date = patch["date"] if "date" in patch and patch["date"] is not None else typed_row["date"]
        amount = patch["amount"] if "amount" in patch and patch["amount"] is not None else typed_row["amount"]
        split_total = cast(
            int | None,
            c.execute(
                "SELECT SUM(amount) FROM splits WHERE transaction_id=?", (tx_id,)
            ).fetchone()[0],
        )
        if split_total is not None and amount != split_total:
            raise HTTPException(400, "edit the split parts before changing the total amount")
        description = patch["description"] if "description" in patch and patch["description"] is not None else typed_row["description"]
        bank_category = patch["bankCategory"] if "bankCategory" in patch and patch["bankCategory"] is not None else typed_row["bank_category"]
        mcc = patch["mcc"] if "mcc" in patch and patch["mcc"] is not None else typed_row["mcc"]
        comment = patch["comment"] if "comment" in patch and patch["comment"] is not None else typed_row["comment"]
        category = typed_row["category_id"]
        if "categoryId" in patch and patch["categoryId"] is not None:
            if split_total is not None:
                raise HTTPException(400, "remove the split before categorizing the parent")
            category = _resolve_category(c, patch["categoryId"], uid, amount)
        elif "amount" in patch and patch["amount"] is not None and category is not None:
            _resolve_category(c, category, uid, amount)
        account = typed_row["account_id"]
        if "accountId" in patch and patch["accountId"] is not None:
            account = _resolve_account(c, patch["accountId"], uid)
        hidden = int(patch["hidden"]) if "hidden" in patch and patch["hidden"] is not None else typed_row["hidden"]
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
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.put("/{tx_id}/splits")
def replace_splits(
    tx_id: int, body: SplitBody, user: Annotated[dict[str, object], Depends(current_user)]
) -> dict[str, list[dict[str, object]]]:
    """Atomically replace every categorized part, or clear the split with an empty list."""
    uid = cast(int, user["id"])
    c = conn()
    try:
        begin_write(c)
        row = c.execute(
            "SELECT t.* FROM transactions t JOIN accounts a ON a.id=t.account_id"
            " WHERE t.id=? AND a.user_id=?",
            (tx_id, uid),
        ).fetchone()
        if not row:
            raise HTTPException(404, "transaction not found")
        typed_row = cast(Mapping[str, object], row)
        if typed_row["transfer_id"] is not None:
            raise HTTPException(400, "transfer transactions cannot be split")
        if body["parts"]:
            if len(body["parts"]) < 2:
                raise HTTPException(400, "a split requires at least two parts")
            if any(part["amount"] == 0 for part in body["parts"]):
                raise HTTPException(400, "split amounts cannot be zero")
            if any((part["amount"] > 0) != (cast(int, typed_row["amount"]) > 0) for part in body["parts"]):
                raise HTTPException(400, "split parts must have the transaction's sign")
            if sum(part["amount"] for part in body["parts"]) != typed_row["amount"]:
                raise HTTPException(400, "split amounts must equal the transaction amount")
            for part in body["parts"]:
                _resolve_category(c, part["categoryId"], uid, part["amount"])
        c.execute("DELETE FROM splits WHERE transaction_id=?", (tx_id,))
        for sort, part in enumerate(body["parts"]):
            c.execute(
                "INSERT INTO splits"
                " (transaction_id, category_id, amount, comment, sort) VALUES (?, ?, ?, ?, ?)",
                (tx_id, part["categoryId"], part["amount"], part.get("comment", ""), sort),
            )
        if body["parts"]:
            c.execute("UPDATE transactions SET category_id=NULL WHERE id=?", (tx_id,))
        c.commit()
        splits = c.execute(
            "SELECT id, category_id, amount, comment FROM splits"
            " WHERE transaction_id=? ORDER BY sort, id",
            (tx_id,),
        )
        return {
            "splits": [
                {
                    "id": part["id"],
                    "categoryId": part["category_id"],
                    "amount": part["amount"],
                    "comment": part["comment"],
                }
                for part in splits
            ]
        }
    finally:
        c.close()


@router.delete("/{tx_id}")
def delete_transaction(
    tx_id: int, user: Annotated[dict[str, object], Depends(current_user)]
) -> dict[str, bool]:
    uid = cast(int, user["id"])
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
        return {"ok": True}
    finally:
        c.close()


@router.post("/bulk")
def bulk_transactions(
    body: BulkBody, user: Annotated[dict[str, object], Depends(current_user)]
) -> dict[str, int]:
    uid = cast(int, user["id"])
    if body["action"] not in ("categorize", "move", "delete"):
        raise HTTPException(400, "action must be 'categorize', 'move' or 'delete'")
    c = conn()
    try:
        begin_write(c)
        affected = 0
        if body["action"] == "delete":
            for tx_id in body["ids"]:
                detach_leg(c, uid, tx_id)
                affected += c.execute(
                    "DELETE FROM transactions WHERE id=?"
                    " AND account_id IN (SELECT id FROM accounts WHERE user_id=?)",
                    (tx_id, uid),
                ).rowcount
        else:
            category = _resolve_category(c, body.get("categoryId"), uid)
            # Validate the complete selection before updating anything. This
            # keeps a mixed bulk selection atomic when one row has the other
            # direction.
            for tx_id in body["ids"]:
                row = c.execute(
                    "SELECT t.amount, EXISTS(SELECT 1 FROM splits s"
                    " WHERE s.transaction_id=t.id) AS is_split"
                    " FROM transactions t JOIN accounts a ON a.id = t.account_id"
                    " WHERE t.id=? AND a.user_id=?",
                    (tx_id, uid),
                ).fetchone()
                if row is not None and row["is_split"]:
                    raise HTTPException(400, "remove the split before categorizing the parent")
                if row is not None and category is not None:
                    _resolve_category(c, category, uid, row["amount"])
            for tx_id in body["ids"]:
                affected += c.execute(
                    "UPDATE transactions SET category_id=? WHERE id=?"
                    " AND account_id IN (SELECT id FROM accounts WHERE user_id=?)",
                    (category, tx_id, uid),
                ).rowcount
        c.commit()
        return {"affected": affected}
    finally:
        c.close()
