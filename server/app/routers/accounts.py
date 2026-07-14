from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..deps import conn, serialize_account
from ..importer import tx_hash

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

TYPES = ("card", "cash", "savings", "other")


class AccountBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: str = "other"
    currency: str = Field(default="RUB", min_length=1, max_length=8)
    openingBalance: int = 0
    openingDate: str | None = None


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    type: str | None = None
    currency: str | None = Field(default=None, min_length=1, max_length=8)
    openingBalance: int | None = None
    openingDate: str | None = None
    archived: bool | None = None


class Reorder(BaseModel):
    ids: list[int]


class ReconcileBody(BaseModel):
    actualBalance: int


@router.get("")
def list_accounts():
    c = conn()
    try:
        return [
            serialize_account(r)
            for r in c.execute(
                "SELECT id, name, type, currency, sort, archived, opening_balance,"
                " opening_date FROM accounts ORDER BY sort, id"
            )
        ]
    finally:
        c.close()


@router.post("")
def create_account(body: AccountBody):
    if body.type not in TYPES:
        raise HTTPException(400, "type must be one of card, cash, savings, other")
    c = conn()
    try:
        if c.execute("SELECT id FROM accounts WHERE name=?", (body.name,)).fetchone():
            raise HTTPException(409, "account with this name already exists")
        max_sort = c.execute("SELECT COALESCE(MAX(sort),0) FROM accounts").fetchone()[0]
        cur = c.execute(
            """INSERT INTO accounts
               (name, type, currency, opening_balance, opening_date, sort)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                body.name,
                body.type,
                body.currency,
                body.openingBalance,
                body.openingDate,
                max_sort + 1,
            ),
        )
        c.commit()
        return {"id": cur.lastrowid}
    finally:
        c.close()


@router.patch("/{account_id}")
def patch_account(account_id: int, patch: AccountPatch):
    c = conn()
    try:
        if not c.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone():
            raise HTTPException(404, "account not found")
        if patch.name is not None:
            dup = c.execute(
                "SELECT id FROM accounts WHERE name=? AND id<>?", (patch.name, account_id)
            ).fetchone()
            if dup:
                raise HTTPException(409, "account with this name already exists")
            c.execute("UPDATE accounts SET name=? WHERE id=?", (patch.name, account_id))
        if patch.type is not None:
            if patch.type not in TYPES:
                raise HTTPException(400, "type must be one of card, cash, savings, other")
            c.execute("UPDATE accounts SET type=? WHERE id=?", (patch.type, account_id))
        if patch.currency is not None:
            c.execute("UPDATE accounts SET currency=? WHERE id=?", (patch.currency, account_id))
        if patch.openingBalance is not None:
            c.execute(
                "UPDATE accounts SET opening_balance=? WHERE id=?",
                (patch.openingBalance, account_id),
            )
        if patch.openingDate is not None:
            c.execute(
                "UPDATE accounts SET opening_date=? WHERE id=?", (patch.openingDate, account_id)
            )
        if patch.archived is not None:
            c.execute(
                "UPDATE accounts SET archived=? WHERE id=?",
                (1 if patch.archived else 0, account_id),
            )
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.delete("/{account_id}")
def delete_account(account_id: int, reassignTo: int | None = None):
    """Deleting an account reassigns its transactions to another account. A
    transaction must always belong to an account, so a non-empty account cannot
    be deleted without a reassign target, and the last account cannot be deleted."""
    c = conn()
    try:
        if not c.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone():
            raise HTTPException(404, "account not found")
        if c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1:
            raise HTTPException(400, "cannot delete the last account")
        has_tx = c.execute(
            "SELECT 1 FROM transactions WHERE account_id=? LIMIT 1", (account_id,)
        ).fetchone()
        if has_tx:
            if reassignTo is None:
                raise HTTPException(400, "account has transactions; a reassign target is required")
            if (
                reassignTo == account_id
                or not c.execute("SELECT id FROM accounts WHERE id=?", (reassignTo,)).fetchone()
            ):
                raise HTTPException(400, "unknown reassign target")
            c.execute(
                "UPDATE transactions SET account_id=? WHERE account_id=?", (reassignTo, account_id)
            )
        c.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.post("/{account_id}/reconcile")
def reconcile_account(account_id: int, body: ReconcileBody):
    """Bring an account's computed balance to the real bank balance by posting a
    single adjustment transaction for the difference. Returns the delta applied."""
    c = conn()
    try:
        acc = c.execute("SELECT opening_balance FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not acc:
            raise HTTPException(404, "account not found")
        total = c.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE account_id=?", (account_id,)
        ).fetchone()[0]
        current = acc["opening_balance"] + total
        delta = body.actualBalance - current
        if delta != 0:
            date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
            desc = "Reconcile adjustment"
            c.execute(
                """INSERT INTO transactions
                   (date, amount, description, account_id, hash, source)
                   VALUES (?, ?, ?, ?, ?, 'adjustment')""",
                (date, delta, desc, account_id, tx_hash(date, delta, desc)),
            )
            c.commit()
        return {"delta": delta}
    finally:
        c.close()


@router.post("/reorder")
def reorder_accounts(body: Reorder):
    c = conn()
    try:
        known = {r["id"] for r in c.execute("SELECT id FROM accounts")}
        if set(body.ids) != known:
            raise HTTPException(400, "ids must list every existing account exactly once")
        for sort, aid in enumerate(body.ids, 1):
            c.execute("UPDATE accounts SET sort=? WHERE id=?", (sort, aid))
        c.commit()
        return {"ok": True}
    finally:
        c.close()
