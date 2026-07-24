from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import current_user
from ..deps import conn, serialize_tx
from ..importer import tx_hash

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

_COUNT_TX = (
    "SELECT COUNT(*) FROM transactions"
    " WHERE account_id IN (SELECT id FROM accounts WHERE user_id=:uid)"
    " AND (:from IS NULL OR date(date) >= date(:from))"
    " AND (:to IS NULL OR date(date) <= date(:to))"
    " AND (:uncat = 0 OR category_id IS NULL)"
    " AND (:uncat = 1 OR :cat IS NULL OR category_id = :cat)"
    " AND (:acct IS NULL OR account_id = :acct)"
    " AND (:q IS NULL OR LOWER(description) LIKE :q)"
)
_LIST_TX = (
    "SELECT * FROM transactions"
    " WHERE account_id IN (SELECT id FROM accounts WHERE user_id=:uid)"
    " AND (:from IS NULL OR date(date) >= date(:from))"
    " AND (:to IS NULL OR date(date) <= date(:to))"
    " AND (:uncat = 0 OR category_id IS NULL)"
    " AND (:uncat = 1 OR :cat IS NULL OR category_id = :cat)"
    " AND (:acct IS NULL OR account_id = :acct)"
    " AND (:q IS NULL OR LOWER(description) LIKE :q)"
    " ORDER BY date DESC, id DESC LIMIT :limit OFFSET :offset"
)


class TxCreate(BaseModel):
    date: str
    amount: int
    accountId: int
    description: str = ""
    bankCategory: str = ""
    mcc: str = ""
    categoryId: int | None = None
    comment: str = ""


class TxPatch(BaseModel):
    date: str | None = None
    amount: int | None = None
    accountId: int | None = None
    description: str | None = None
    bankCategory: str | None = None
    mcc: str | None = None
    categoryId: int | None = None
    comment: str | None = None


class BulkBody(BaseModel):
    action: str
    ids: list[int]
    categoryId: int | None = None


def _resolve_category(c, category_id, uid):
    """
    0 (or None handled by caller) means uncategorized; else must exist.
    """
    if category_id in (None, 0):
        return None
    if not c.execute(
        "SELECT c.id FROM categories c JOIN category_groups g ON g.id = c.group_id"
        " WHERE c.id=? AND g.user_id=?",
        (category_id, uid),
    ).fetchone():
        raise HTTPException(400, "unknown category")
    return category_id


def _resolve_account(c, account_id, uid):
    if not c.execute(
        "SELECT id FROM accounts WHERE id=? AND user_id=?", (account_id, uid)
    ).fetchone():
        raise HTTPException(400, "unknown account")
    return account_id


@router.get("")
def list_transactions(
    user: Annotated[dict, Depends(current_user)],
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    categoryId: int | None = None,
    accountId: int | None = None,
    uncategorized: bool = False,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    uid = user["id"]
    params = {
        "uid": uid,
        "from": from_,
        "to": to,
        "uncat": 1 if uncategorized else 0,
        "cat": categoryId,
        "acct": accountId,
        "q": f"%{q.lower()}%" if q else None,
        "limit": limit,
        "offset": offset,
    }
    c = conn()
    try:
        total = c.execute(_COUNT_TX, params).fetchone()[0]
        rows = c.execute(_LIST_TX, params)
        return {"total": total, "rows": [serialize_tx(r) for r in rows]}
    finally:
        c.close()


@router.post("")
def create_transaction(body: TxCreate, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        category = _resolve_category(c, body.categoryId, uid)
        account = _resolve_account(c, body.accountId, uid)
        cur = c.execute(
            """INSERT INTO transactions
               (date, amount, description, bank_category, mcc, category_id, account_id,
                comment, hash, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual')""",
            (
                body.date,
                body.amount,
                body.description,
                body.bankCategory,
                body.mcc,
                category,
                account,
                body.comment,
                tx_hash(body.date, body.amount, body.description),
            ),
        )
        c.commit()
        return {"id": cur.lastrowid}
    finally:
        c.close()


@router.patch("/{tx_id}")
def patch_transaction(tx_id: int, patch: TxPatch, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        row = c.execute(
            "SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id"
            " WHERE t.id=? AND a.user_id=?",
            (tx_id, uid),
        ).fetchone()
        if not row:
            raise HTTPException(404, "transaction not found")
        date = patch.date if patch.date is not None else row["date"]
        amount = patch.amount if patch.amount is not None else row["amount"]
        description = patch.description if patch.description is not None else row["description"]
        bank_category = (
            patch.bankCategory if patch.bankCategory is not None else row["bank_category"]
        )
        mcc = patch.mcc if patch.mcc is not None else row["mcc"]
        comment = patch.comment if patch.comment is not None else row["comment"]
        category = row["category_id"]
        if patch.categoryId is not None:
            category = _resolve_category(c, patch.categoryId, uid)
        account = row["account_id"]
        if patch.accountId is not None:
            account = _resolve_account(c, patch.accountId, uid)
        c.execute(
            """UPDATE transactions
               SET date=?, amount=?, description=?, bank_category=?, mcc=?, category_id=?,
                   account_id=?, comment=?, hash=?
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
                tx_hash(date, amount, description),
                tx_id,
            ),
        )
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.delete("/{tx_id}")
def delete_transaction(tx_id: int, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
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
def bulk_transactions(body: BulkBody, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    if body.action not in ("categorize", "move", "delete"):
        raise HTTPException(400, "action must be 'categorize', 'move' or 'delete'")
    c = conn()
    try:
        affected = 0
        if body.action == "delete":
            for tx_id in body.ids:
                affected += c.execute(
                    "DELETE FROM transactions WHERE id=?"
                    " AND account_id IN (SELECT id FROM accounts WHERE user_id=?)",
                    (tx_id, uid),
                ).rowcount
        else:
            category = _resolve_category(c, body.categoryId, uid)
            for tx_id in body.ids:
                affected += c.execute(
                    "UPDATE transactions SET category_id=? WHERE id=?"
                    " AND account_id IN (SELECT id FROM accounts WHERE user_id=?)",
                    (category, tx_id, uid),
                ).rowcount
        c.commit()
        return {"affected": affected}
    finally:
        c.close()
