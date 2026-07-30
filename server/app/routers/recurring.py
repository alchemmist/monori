import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import current_user
from ..db import begin_write
from ..deps import conn
from ..importer import tx_hash

router = APIRouter(prefix="/api/recurring", tags=["recurring"])


class RecurringBody(BaseModel):
    accountId: int
    categoryId: int | None = None
    payee: str = ""
    description: str = ""
    amount: int
    frequency: Literal["daily", "weekly", "monthly", "yearly"]
    interval: int = Field(default=1, ge=1, le=366)
    startDate: date
    endDate: date | None = None
    autoCreate: bool = True


def _serialize(row):
    return {
        "id": row["id"],
        "accountId": row["account_id"],
        "categoryId": row["category_id"],
        "payee": row["payee"],
        "description": row["description"],
        "amount": row["amount"],
        "frequency": row["frequency"],
        "interval": row["interval"],
        "startDate": row["start_date"],
        "nextDate": row["next_date"],
        "endDate": row["end_date"],
        "autoCreate": bool(row["auto_create"]),
        "active": bool(row["active"]),
    }


def _advance(value: date, frequency: str, interval: int):
    if frequency == "daily":
        return value + timedelta(days=interval)
    if frequency == "weekly":
        return value + timedelta(weeks=interval)
    months = interval if frequency == "monthly" else interval * 12
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _validate_refs(c, uid, body):
    if not c.execute(
        "SELECT 1 FROM accounts WHERE id=? AND user_id=?", (body.accountId, uid)
    ).fetchone():
        raise HTTPException(400, "unknown account")
    if body.categoryId is not None:
        category = c.execute(
            "SELECT t.transaction_sign FROM categories c"
            " JOIN category_groups g ON g.id=c.group_id"
            " JOIN category_group_types t ON t.id=g.type_id"
            " WHERE c.id=? AND g.user_id=?",
            (body.categoryId, uid),
        ).fetchone()
        if not category:
            raise HTTPException(400, "unknown category")
        expected = -1 if body.amount < 0 else 1
        if category["transaction_sign"] != expected:
            raise HTTPException(400, "category does not match transaction direction")
    if body.endDate is not None and body.endDate < body.startDate:
        raise HTTPException(400, "end date must not precede start date")


def _materialize(c, uid, today=None):
    today = today or date.today()
    created = []
    reminders = []
    rows = c.execute(
        "SELECT * FROM recurring_transactions WHERE user_id=? AND active=1",
        (uid,),
    ).fetchall()
    for row in rows:
        due = date.fromisoformat(row["next_date"])
        end = date.fromisoformat(row["end_date"]) if row["end_date"] else None
        while due <= today and (end is None or due <= end):
            transaction_id = None
            if row["auto_create"]:
                timestamp = f"{due.isoformat()}T12:00:00"
                cur = c.execute(
                    """INSERT INTO transactions
                    (date, amount, description, bank_category, mcc, category_id, account_id,
                     comment, hash, source)
                    VALUES (?, ?, ?, '', '', ?, ?, ?, ?, 'recurring')""",
                    (
                        timestamp,
                        row["amount"],
                        row["payee"],
                        row["category_id"],
                        row["account_id"],
                        row["description"],
                        tx_hash(row["account_id"], timestamp, row["amount"], row["payee"]),
                    ),
                )
                transaction_id = cur.lastrowid
                created.append(transaction_id)
            else:
                reminders.append(row["id"])
            c.execute(
                "INSERT OR IGNORE INTO recurring_occurrences"
                " (recurring_id, due_date, transaction_id) VALUES (?, ?, ?)",
                (row["id"], due.isoformat(), transaction_id),
            )
            due = _advance(due, row["frequency"], row["interval"])
        active = not (end is not None and due > end)
        c.execute(
            "UPDATE recurring_transactions SET next_date=?, active=? WHERE id=?",
            (due.isoformat(), int(active), row["id"]),
        )
    return created, reminders


@router.get("")
def list_recurring(user: Annotated[dict, Depends(current_user)]):
    c = conn()
    try:
        begin_write(c)
        created, reminders = _materialize(c, user["id"])
        rows = c.execute(
            "SELECT * FROM recurring_transactions WHERE user_id=?"
            " ORDER BY active DESC, next_date, id",
            (user["id"],),
        ).fetchall()
        c.commit()
        return {
            "rows": [_serialize(row) for row in rows],
            "createdTransactionIds": created,
            "dueReminderIds": reminders,
        }
    finally:
        c.close()


@router.post("")
def create_recurring(body: RecurringBody, user: Annotated[dict, Depends(current_user)]):
    c = conn()
    try:
        _validate_refs(c, user["id"], body)
        now = datetime.now(UTC).isoformat()
        cur = c.execute(
            """INSERT INTO recurring_transactions
            (user_id, account_id, category_id, payee, description, amount, frequency, interval,
             start_date, next_date, end_date, auto_create, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user["id"],
                body.accountId,
                body.categoryId,
                body.payee,
                body.description,
                body.amount,
                body.frequency,
                body.interval,
                body.startDate.isoformat(),
                body.startDate.isoformat(),
                body.endDate.isoformat() if body.endDate else None,
                int(body.autoCreate),
                now,
            ),
        )
        c.commit()
        return {"id": cur.lastrowid}
    finally:
        c.close()


@router.delete("/{recurring_id}")
def delete_recurring(recurring_id: int, user: Annotated[dict, Depends(current_user)]):
    c = conn()
    try:
        cur = c.execute(
            "DELETE FROM recurring_transactions WHERE id=? AND user_id=?",
            (recurring_id, user["id"]),
        )
        if not cur.rowcount:
            raise HTTPException(404, "recurring transaction not found")
        c.commit()
        return {"ok": True}
    finally:
        c.close()
