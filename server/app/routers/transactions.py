import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import current_user
from ..db import begin_write
from ..deps import conn, serialize_transactions
from ..importer import tx_hash
from ..transfer_service import detach_leg

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


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
    hidden: bool | None = None


class BulkBody(BaseModel):
    action: str
    ids: list[int]
    categoryId: int | None = None


class SplitPart(BaseModel):
    categoryId: int
    amount: int
    comment: str = ""


class SplitBody(BaseModel):
    parts: list[SplitPart]


class RefundBody(BaseModel):
    originalId: int


def _validate_category_type(transaction_sign, amount, is_refund=False):
    if amount < 0 and transaction_sign != -1:
        raise HTTPException(400, "expense transaction requires an expense category")
    if is_refund and transaction_sign != -1:
        raise HTTPException(400, "refund requires an expense category")


def _resolve_category(c, category_id, uid, amount=None, is_refund=False):
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
        _validate_category_type(category["transaction_sign"], amount, is_refund)
    return category_id


def _owned_transaction(c, tx_id, uid):
    return c.execute(
        "SELECT t.* FROM transactions t JOIN accounts a ON a.id=t.account_id"
        " WHERE t.id=? AND a.user_id=?",
        (tx_id, uid),
    ).fetchone()


def _refund_total(c, original_id, excluding=None):
    return c.execute(
        "SELECT COALESCE(SUM(t.amount), 0) FROM refund_links r"
        " JOIN transactions t ON t.id=r.refund_tx_id"
        " WHERE r.original_tx_id=? AND (? IS NULL OR r.refund_tx_id<>?)",
        (original_id, excluding, excluding),
    ).fetchone()[0]


def _merchant_key(value):
    # Keep this server-side twin in sync with web/src/engine/refunds.js.
    value = re.sub(r"(?<![a-zа-яё])(refund|return|возврат)(?![a-zа-яё])", " ", value.lower())
    return " ".join(re.findall(r"[a-zа-яё]+", value))


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
    hidden: bool = False,
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
        return {"total": total, "rows": serialize_transactions(c, rows)}
    finally:
        c.close()


@router.post("")
def create_transaction(body: TxCreate, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        category = _resolve_category(c, body.categoryId, uid, body.amount)
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
                tx_hash(account, body.date, body.amount, body.description),
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
        begin_write(c)
        row = c.execute(
            "SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id"
            " WHERE t.id=? AND a.user_id=?",
            (tx_id, uid),
        ).fetchone()
        if not row:
            raise HTTPException(404, "transaction not found")
        refund_link = c.execute(
            "SELECT original_tx_id FROM refund_links WHERE refund_tx_id=?", (tx_id,)
        ).fetchone()
        date = patch.date if patch.date is not None else row["date"]
        amount = patch.amount if patch.amount is not None else row["amount"]
        if refund_link:
            if amount <= 0:
                raise HTTPException(400, "a linked refund must remain positive")
            original = _owned_transaction(c, refund_link["original_tx_id"], uid)
            if _refund_total(c, original["id"], tx_id) + amount > -original["amount"]:
                raise HTTPException(400, "refunds cannot exceed the original purchase")
        linked_total = _refund_total(c, tx_id)
        if linked_total and (amount >= 0 or linked_total > -amount):
            raise HTTPException(400, "purchase amount cannot be less than its refunds")
        split_total = c.execute(
            "SELECT SUM(amount) FROM splits WHERE transaction_id=?", (tx_id,)
        ).fetchone()[0]
        if split_total is not None and amount != split_total:
            raise HTTPException(400, "edit the split parts before changing the total amount")
        description = patch.description if patch.description is not None else row["description"]
        bank_category = (
            patch.bankCategory if patch.bankCategory is not None else row["bank_category"]
        )
        mcc = patch.mcc if patch.mcc is not None else row["mcc"]
        comment = patch.comment if patch.comment is not None else row["comment"]
        category = row["category_id"]
        if patch.categoryId is not None:
            if split_total is not None:
                raise HTTPException(400, "remove the split before categorizing the parent")
            category = _resolve_category(c, patch.categoryId, uid, amount, bool(refund_link))
        elif patch.amount is not None and category is not None:
            _resolve_category(c, category, uid, amount, bool(refund_link))
        account = row["account_id"]
        if patch.accountId is not None:
            account = _resolve_account(c, patch.accountId, uid)
        hidden = int(patch.hidden) if patch.hidden is not None else row["hidden"]
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


@router.get("/{refund_tx_id}/refund-suggestions")
def refund_suggestions(refund_tx_id: int, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        refund = _owned_transaction(c, refund_tx_id, uid)
        if not refund:
            raise HTTPException(404, "transaction not found")
        if refund["amount"] <= 0:
            raise HTTPException(400, "only a positive transaction can be a refund")
        if refund["transfer_id"] is not None:
            raise HTTPException(400, "transfer transactions cannot be refunds")
        if c.execute(
            "SELECT 1 FROM splits WHERE transaction_id=? LIMIT 1", (refund_tx_id,)
        ).fetchone():
            raise HTTPException(400, "split transactions cannot be refunds")
        key = _merchant_key(refund["description"])
        current_link = c.execute(
            "SELECT original_tx_id FROM refund_links WHERE refund_tx_id=?", (refund_tx_id,)
        ).fetchone()
        current_original_id = current_link["original_tx_id"] if current_link else None
        rows = c.execute(
            "SELECT t.*, COALESCE((SELECT SUM(rt.amount) FROM refund_links rl"
            " JOIN transactions rt ON rt.id=rl.refund_tx_id"
            " WHERE rl.original_tx_id=t.id AND rl.refund_tx_id<>?), 0) AS used_refund"
            " FROM transactions t JOIN accounts a ON a.id=t.account_id"
            " WHERE a.user_id=? AND t.amount<0 AND t.date<=?"
            " AND t.transfer_id IS NULL AND t.id<>?"
            " AND NOT EXISTS (SELECT 1 FROM splits s WHERE s.transaction_id=t.id)"
            " ORDER BY t.date DESC, t.id DESC LIMIT 250",
            (refund_tx_id, uid, refund["date"], refund_tx_id),
        ).fetchall()
        candidates = []
        for row in rows:
            used = row["used_refund"]
            remaining = -row["amount"] - used
            if remaining < refund["amount"]:
                continue
            same_merchant = bool(key) and _merchant_key(row["description"]) == key
            if (
                row["id"] != current_original_id
                and not same_merchant
                and -row["amount"] != refund["amount"]
            ):
                continue
            candidates.append((not same_merchant, row))
        candidates.sort(key=lambda item: item[0])
        return {"rows": serialize_transactions(c, [row for _, row in candidates[:20]])}
    finally:
        c.close()


@router.put("/{refund_tx_id}/refund")
def link_refund(refund_tx_id: int, body: RefundBody, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        begin_write(c)
        refund = _owned_transaction(c, refund_tx_id, uid)
        original = _owned_transaction(c, body.originalId, uid)
        if not refund or not original:
            raise HTTPException(404, "transaction not found")
        if refund["amount"] <= 0 or original["amount"] >= 0:
            raise HTTPException(400, "a refund must link a positive transaction to a purchase")
        if refund["transfer_id"] is not None or original["transfer_id"] is not None:
            raise HTTPException(400, "transfer transactions cannot be refunds")
        if c.execute(
            "SELECT 1 FROM splits WHERE transaction_id IN (?, ?) LIMIT 1",
            (refund_tx_id, body.originalId),
        ).fetchone():
            raise HTTPException(400, "split transactions cannot be refunds")
        if c.execute(
            "SELECT 1 FROM refund_links WHERE refund_tx_id=? OR original_tx_id=? LIMIT 1",
            (body.originalId, refund_tx_id),
        ).fetchone():
            raise HTTPException(400, "refund links cannot be chained")
        if _refund_total(c, body.originalId, refund_tx_id) + refund["amount"] > -original["amount"]:
            raise HTTPException(400, "refunds cannot exceed the original purchase")
        c.execute(
            "INSERT INTO refund_links (refund_tx_id, original_tx_id) VALUES (?, ?)"
            " ON CONFLICT(refund_tx_id) DO UPDATE SET original_tx_id=excluded.original_tx_id",
            (refund_tx_id, body.originalId),
        )
        c.execute(
            "UPDATE transactions SET category_id=? WHERE id=?",
            (original["category_id"], refund_tx_id),
        )
        c.commit()
        return {
            "ok": True,
            "refundOfId": body.originalId,
            "categoryId": original["category_id"],
        }
    finally:
        c.close()


@router.delete("/{refund_tx_id}/refund")
def unlink_refund(refund_tx_id: int, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        begin_write(c)
        refund = _owned_transaction(c, refund_tx_id, uid)
        if not refund:
            raise HTTPException(404, "transaction not found")
        deleted = c.execute(
            "DELETE FROM refund_links WHERE refund_tx_id=?", (refund_tx_id,)
        ).rowcount
        if not deleted:
            raise HTTPException(404, "refund link not found")
        c.commit()
        return {"ok": True, "categoryId": refund["category_id"]}
    finally:
        c.close()


@router.put("/{tx_id}/splits")
def replace_splits(tx_id: int, body: SplitBody, user: Annotated[dict, Depends(current_user)]):
    """Atomically replace every categorized part, or clear the split with an empty list."""
    uid = user["id"]
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
        if row["transfer_id"] is not None:
            raise HTTPException(400, "transfer transactions cannot be split")
        if body.parts:
            if c.execute(
                "SELECT 1 FROM refund_links WHERE refund_tx_id=? OR original_tx_id=? LIMIT 1",
                (tx_id, tx_id),
            ).fetchone():
                raise HTTPException(400, "refund transactions cannot be split")
            if len(body.parts) < 2:
                raise HTTPException(400, "a split requires at least two parts")
            if any(part.amount == 0 for part in body.parts):
                raise HTTPException(400, "split amounts cannot be zero")
            if any((part.amount > 0) != (row["amount"] > 0) for part in body.parts):
                raise HTTPException(400, "split parts must have the transaction's sign")
            if sum(part.amount for part in body.parts) != row["amount"]:
                raise HTTPException(400, "split amounts must equal the transaction amount")
            for part in body.parts:
                _resolve_category(c, part.categoryId, uid, part.amount)
        c.execute("DELETE FROM splits WHERE transaction_id=?", (tx_id,))
        for sort, part in enumerate(body.parts):
            c.execute(
                "INSERT INTO splits"
                " (transaction_id, category_id, amount, comment, sort) VALUES (?, ?, ?, ?, ?)",
                (tx_id, part.categoryId, part.amount, part.comment, sort),
            )
        if body.parts:
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
def delete_transaction(tx_id: int, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
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
def bulk_transactions(body: BulkBody, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
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
            category = _resolve_category(c, body.categoryId, uid)
            # Validate the complete selection before updating anything. This
            # keeps a mixed bulk selection atomic when one row has the other
            # direction.
            for tx_id in body.ids:
                row = c.execute(
                    "SELECT t.amount, EXISTS(SELECT 1 FROM splits s"
                    " WHERE s.transaction_id=t.id) AS is_split"
                    ", EXISTS(SELECT 1 FROM refund_links r"
                    " WHERE r.refund_tx_id=t.id) AS is_refund"
                    " FROM transactions t JOIN accounts a ON a.id = t.account_id"
                    " WHERE t.id=? AND a.user_id=?",
                    (tx_id, uid),
                ).fetchone()
                if row is not None and row["is_split"]:
                    raise HTTPException(400, "remove the split before categorizing the parent")
                if row is not None and category is not None:
                    _resolve_category(c, category, uid, row["amount"], bool(row["is_refund"]))
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
