"""
Admin panel API: instance-wide analytics and user management.

Every route requires the ``admin_user`` dependency (403 otherwise). The admin
sees full user data — this is the instance owner's own deployment.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..admin import admin_user
from ..deps import conn, serialize_user
from .auth_router import create_user

router = APIRouter(prefix="/api/admin", tags=["admin"])

RECENT_TX_LIMIT = 50
RECENT_LOGINS_LIMIT = 50
ACTIVITY_WINDOW_DAYS = 30


def _cutoff(days):
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def _count(c, sql, params=()):
    return c.execute(sql, params).fetchone()[0]


@router.get("/overview")
def overview(admin: Annotated[dict, Depends(admin_user)]):
    c = conn()
    try:
        cutoff7, cutoff30 = _cutoff(7), _cutoff(30)
        active = _count(
            c,
            "SELECT COUNT(*) FROM (SELECT user_id FROM feature_usage WHERE day >= ?"
            " UNION SELECT user_id FROM activity_events WHERE created_at >= ?)",
            (cutoff7[:10], cutoff7),
        )
        return {
            "totals": {
                "users": _count(c, "SELECT COUNT(*) FROM users"),
                "transactions": _count(c, "SELECT COUNT(*) FROM transactions"),
                "accounts": _count(c, "SELECT COUNT(*) FROM accounts"),
                "connections": _count(c, "SELECT COUNT(*) FROM bank_connections"),
            },
            "newUsers7d": _count(c, "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoff7,)),
            "newUsers30d": _count(
                c, "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoff30,)
            ),
            "activeUsers7d": active,
            "registrations": [
                {"month": r["m"], "count": r["n"]}
                for r in c.execute(
                    "SELECT substr(created_at, 1, 7) AS m, COUNT(*) AS n FROM users"
                    " GROUP BY m ORDER BY m"
                )
            ],
        }
    finally:
        c.close()


@router.get("/users")
def list_users(admin: Annotated[dict, Depends(admin_user)]):
    c = conn()
    try:
        connections = {}
        for r in c.execute(
            "SELECT user_id, status, last_sync, last_error FROM bank_connections ORDER BY id"
        ):
            connections[r["user_id"]] = {
                "status": r["status"],
                "lastSync": r["last_sync"],
                "lastError": r["last_error"],
            }
        return [
            {
                "id": r["id"],
                "email": r["email"],
                "createdAt": r["created_at"],
                "lastLogin": r["last_login"],
                "isAdmin": bool(r["is_admin"]),
                "accounts": r["accounts"],
                "transactions": r["transactions"],
                "lastTransaction": r["last_tx"],
                "budgets": r["budgets"],
                "connection": connections.get(r["id"]),
            }
            for r in c.execute(
                "SELECT u.id, u.email, u.created_at, u.last_login, u.is_admin,"
                " (SELECT COUNT(*) FROM accounts a WHERE a.user_id = u.id) AS accounts,"
                " (SELECT COUNT(*) FROM transactions t JOIN accounts a ON a.id = t.account_id"
                "  WHERE a.user_id = u.id) AS transactions,"
                " (SELECT MAX(t.date) FROM transactions t JOIN accounts a ON a.id = t.account_id"
                "  WHERE a.user_id = u.id) AS last_tx,"
                " (SELECT COUNT(*) FROM budgets b JOIN categories cat ON cat.id = b.category_id"
                "  JOIN category_groups g ON g.id = cat.group_id WHERE g.user_id = u.id)"
                "  AS budgets"
                " FROM users u ORDER BY u.id"
            )
        ]
    finally:
        c.close()


@router.get("/users/{uid}")
def user_detail(uid: int, admin: Annotated[dict, Depends(admin_user)]):
    c = conn()
    try:
        row = c.execute(
            "SELECT id, email, created_at, is_admin, last_login FROM users WHERE id=?", (uid,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "unknown user")
        return {
            "user": serialize_user(row),
            "accounts": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "type": r["type"],
                    "currency": r["currency"],
                    "archived": bool(r["archived"]),
                    "balance": r["balance"],
                    "transactions": r["tx_count"],
                }
                for r in c.execute(
                    "SELECT a.id, a.name, a.type, a.currency, a.archived,"
                    " a.opening_balance + COALESCE(SUM(t.amount), 0) AS balance,"
                    " COUNT(t.id) AS tx_count"
                    " FROM accounts a LEFT JOIN transactions t ON t.account_id = a.id"
                    " WHERE a.user_id=? GROUP BY a.id ORDER BY a.sort, a.id",
                    (uid,),
                )
            ],
            "recentTransactions": [
                {
                    "id": r["id"],
                    "date": r["date"],
                    "amount": r["amount"],
                    "description": r["description"],
                    "account": r["account_name"],
                    "category": r["category_name"],
                }
                for r in c.execute(
                    "SELECT t.id, t.date, t.amount, t.description,"
                    " a.name AS account_name, cat.name AS category_name"
                    " FROM transactions t JOIN accounts a ON a.id = t.account_id"
                    " LEFT JOIN categories cat ON cat.id = t.category_id"
                    " WHERE a.user_id=? ORDER BY t.date DESC, t.id DESC LIMIT ?",
                    (uid, RECENT_TX_LIMIT),
                )
            ],
            "featureUsage": [
                {"feature": r["feature"], "count": r["n"]}
                for r in c.execute(
                    "SELECT feature, SUM(count) AS n FROM feature_usage WHERE user_id=?"
                    " GROUP BY feature ORDER BY n DESC",
                    (uid,),
                )
            ],
            "recentLogins": [
                r["created_at"]
                for r in c.execute(
                    "SELECT created_at FROM activity_events WHERE user_id=? AND kind='login'"
                    " ORDER BY id DESC LIMIT ?",
                    (uid, RECENT_LOGINS_LIMIT),
                )
            ],
        }
    finally:
        c.close()


@router.get("/users/{uid}/transactions")
def user_transactions(uid: int, admin: Annotated[dict, Depends(admin_user)]):
    """
    Every transaction of a user, newest first — the full list behind the detail
    view's preview, rendered as one JSON object per line by the client.
    """
    c = conn()
    try:
        if c.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone() is None:
            raise HTTPException(404, "unknown user")
        return [
            {
                "id": r["id"],
                "date": r["date"],
                "amount": r["amount"],
                "description": r["description"],
                "account": r["account_name"],
                "category": r["category_name"],
                "mcc": r["mcc"],
                "comment": r["comment"],
                "source": r["source"],
            }
            for r in c.execute(
                "SELECT t.id, t.date, t.amount, t.description, t.mcc, t.comment, t.source,"
                " a.name AS account_name, cat.name AS category_name"
                " FROM transactions t JOIN accounts a ON a.id = t.account_id"
                " LEFT JOIN categories cat ON cat.id = t.category_id"
                " WHERE a.user_id=? ORDER BY t.date DESC, t.id DESC",
                (uid,),
            )
        ]
    finally:
        c.close()


class CreateUserBody(BaseModel):
    email: str
    password: str


@router.post("/users")
def create_user_admin(body: CreateUserBody, admin: Annotated[dict, Depends(admin_user)]):
    c = conn()
    try:
        return create_user(c, body.email, body.password)
    finally:
        c.close()


@router.delete("/users/{uid}")
def delete_user(uid: int, admin: Annotated[dict, Depends(admin_user)]):
    if uid == admin["id"]:
        raise HTTPException(400, "cannot delete yourself")
    c = conn()
    try:
        if c.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone() is None:
            raise HTTPException(404, "unknown user")
        # order respects the accounts <-> bank_connections FK cycle; budgets,
        # activity_events and feature_usage go via ON DELETE CASCADE
        c.execute("UPDATE bank_connections SET pending_account_id=NULL WHERE user_id=?", (uid,))
        c.execute(
            "DELETE FROM transactions WHERE account_id IN"
            " (SELECT id FROM accounts WHERE user_id=?)",
            (uid,),
        )
        c.execute("DELETE FROM accounts WHERE user_id=?", (uid,))
        c.execute("DELETE FROM bank_connections WHERE user_id=?", (uid,))
        c.execute(
            "DELETE FROM categories WHERE group_id IN"
            " (SELECT id FROM category_groups WHERE user_id=?)",
            (uid,),
        )
        c.execute("DELETE FROM category_groups WHERE user_id=?", (uid,))
        c.execute("DELETE FROM users WHERE id=?", (uid,))
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.get("/activity")
def activity(admin: Annotated[dict, Depends(admin_user)]):
    c = conn()
    try:
        day_cutoff = _cutoff(ACTIVITY_WINDOW_DAYS)[:10]
        return {
            "features": [
                {"feature": r["feature"], "count": r["n"]}
                for r in c.execute(
                    "SELECT feature, SUM(count) AS n FROM feature_usage WHERE day >= ?"
                    " GROUP BY feature ORDER BY n DESC",
                    (day_cutoff,),
                )
            ],
            "daily": [
                {"day": r["day"], "count": r["n"]}
                for r in c.execute(
                    "SELECT day, SUM(count) AS n FROM feature_usage WHERE day >= ?"
                    " GROUP BY day ORDER BY day",
                    (day_cutoff,),
                )
            ],
            "recentLogins": [
                {"email": r["email"], "at": r["created_at"]}
                for r in c.execute(
                    "SELECT u.email, e.created_at FROM activity_events e"
                    " JOIN users u ON u.id = e.user_id WHERE e.kind='login'"
                    " ORDER BY e.id DESC LIMIT ?",
                    (RECENT_LOGINS_LIMIT,),
                )
            ],
        }
    finally:
        c.close()
