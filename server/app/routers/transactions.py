from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..deps import conn, serialize_tx
from ..importer import tx_hash

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

_WHERE_TX = (
    " WHERE (:from IS NULL OR date(date) >= date(:from))"
    " AND (:to IS NULL OR date(date) <= date(:to))"
    " AND (:uncat = 0 OR category_id IS NULL)"
    " AND (:uncat = 1 OR :cat IS NULL OR category_id = :cat)"
    " AND (:acct IS NULL OR account_id = :acct)"
    " AND (:q IS NULL OR LOWER(description) LIKE :q)"
)
_COUNT_TX = "SELECT COUNT(*) FROM transactions" + _WHERE_TX
_LIST_TX = (
    "SELECT * FROM transactions"
    + _WHERE_TX
    + " ORDER BY date DESC, id DESC LIMIT :limit OFFSET :offset"
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


def _resolve_category(c, category_id):
    """0 (or None handled by caller) means uncategorized; else must exist."""
    if category_id in (None, 0):
        return None
    if not c.execute("SELECT id FROM categories WHERE id=?", (category_id,)).fetchone():
        raise HTTPException(400, "unknown category")
    return category_id


def _resolve_account(c, account_id):
    if not c.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone():
        raise HTTPException(400, "unknown account")
    return account_id


@router.get("")
def list_transactions(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    categoryId: int | None = None,
    accountId: int | None = None,
    uncategorized: bool = False,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    params = {
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
def create_transaction(body: TxCreate):
    c = conn()
    try:
        category = _resolve_category(c, body.categoryId)
        account = _resolve_account(c, body.accountId)
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
def patch_transaction(tx_id: int, patch: TxPatch):
    c = conn()
    try:
        row = c.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
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
            category = _resolve_category(c, patch.categoryId)
        account = row["account_id"]
        if patch.accountId is not None:
            account = _resolve_account(c, patch.accountId)
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
def delete_transaction(tx_id: int):
    c = conn()
    try:
        cur = c.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
        c.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "transaction not found")
        return {"ok": True}
    finally:
        c.close()


@router.post("/bulk")
def bulk_transactions(body: BulkBody):
    if body.action not in ("categorize", "move", "delete"):
        raise HTTPException(400, "action must be 'categorize', 'move' or 'delete'")
    c = conn()
    try:
        affected = 0
        if body.action == "delete":
            for tx_id in body.ids:
                affected += c.execute("DELETE FROM transactions WHERE id=?", (tx_id,)).rowcount
        else:
            category = _resolve_category(c, body.categoryId)
            for tx_id in body.ids:
                affected += c.execute(
                    "UPDATE transactions SET category_id=? WHERE id=?", (category, tx_id)
                ).rowcount
        c.commit()
        return {"affected": affected}
    finally:
        c.close()
