"""
Admin panel API: instance-wide analytics and user management.

Every route requires the ``admin_user`` dependency (403 otherwise). The admin
sees full user data — this is the instance owner's own deployment.
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from .. import auth
from ..admin import admin_user
from ..db_records import UserRecord
from ..deps import UserResponse, conn, serialize_user
from .auth_router import create_user

router = APIRouter(prefix="/api/admin", tags=["admin"])
type AdminContext = auth.AuthenticatedUser

RECENT_TX_LIMIT = 50
TX_PAGE_MAX = 1000
SQL_CHUNK = 500
RECENT_LOGINS_LIMIT = 50
ACTIVITY_WINDOW_DAYS = 30


def _cutoff(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def _count(c: sqlite3.Connection, sql: str) -> int:
    row = c.execute(sql).fetchone()
    if row is None or not isinstance(row[0], int):
        raise RuntimeError("count query did not return an integer")
    return row[0]


def _count_since(c: sqlite3.Connection, sql: str, since: str) -> int:
    row = c.execute(sql, (since,)).fetchone()
    if row is None or not isinstance(row[0], int):
        raise RuntimeError("count query did not return an integer")
    return row[0]


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class AdminTotals:
    users: int
    transactions: int
    accounts: int
    connections: int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class RegistrationCount:
    month: str
    count: int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class OverviewResponse:
    totals: AdminTotals
    dbSizeBytes: int
    newUsers7d: int
    newUsers30d: int
    activeUsers7d: int
    registrations: list[RegistrationCount]


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class AdminConnectionSummary:
    status: str
    lastSync: str | None
    lastError: str | None


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class AdminUserSummary:
    id: int
    email: str
    createdAt: str
    lastLogin: str | None
    isAdmin: bool
    accounts: int
    transactions: int
    lastTransaction: str | None
    budgets: int
    connection: AdminConnectionSummary | None


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class AdminAccountSummary:
    id: int
    name: str
    type: str
    currency: str
    archived: bool
    balance: int
    transactions: int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class AdminTransactionSummary:
    id: int
    date: str
    amount: int
    description: str
    account: str
    category: str | None


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class AdminTransactionDetail(AdminTransactionSummary):
    mcc: str
    comment: str
    source: str


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class FeatureCount:
    feature: str
    count: int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class UserDetailResponse:
    user: UserResponse
    accounts: list[AdminAccountSummary]
    recentTransactions: list[AdminTransactionSummary]
    featureUsage: list[FeatureCount]
    recentLogins: list[str]


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class DayCount:
    day: str
    count: int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class LoginEvent:
    email: str
    at: str


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class ActivityResponse:
    features: list[FeatureCount]
    daily: list[DayCount]
    recentLogins: list[LoginEvent]


@router.get("/overview")
def overview(admin: Annotated[AdminContext, Depends(admin_user)]) -> OverviewResponse:
    c = conn()
    try:
        cutoff7, cutoff30 = _cutoff(7), _cutoff(30)
        active_row = c.execute(
            "SELECT COUNT(*) FROM (SELECT user_id FROM feature_usage WHERE day >= ?"
            " UNION SELECT user_id FROM activity_events WHERE created_at >= ?)",
            (cutoff7[:10], cutoff7),
        ).fetchone()
        if active_row is None or not isinstance(active_row[0], int):
            raise RuntimeError("active user query did not return an integer")
        return OverviewResponse(
            totals=AdminTotals(
                users=_count(c, "SELECT COUNT(*) FROM users"),
                transactions=_count(c, "SELECT COUNT(*) FROM transactions"),
                accounts=_count(c, "SELECT COUNT(*) FROM accounts"),
                connections=_count(c, "SELECT COUNT(*) FROM bank_connections"),
            ),
            # pragmas rather than a filesystem stat: the connection knows the
            # database regardless of where (or whether) the file lives
            dbSizeBytes=_count(c, "PRAGMA page_count") * _count(c, "PRAGMA page_size"),
            newUsers7d=_count_since(c, "SELECT COUNT(*) FROM users WHERE created_at >= ?", cutoff7),
            newUsers30d=_count_since(
                c, "SELECT COUNT(*) FROM users WHERE created_at >= ?", cutoff30
            ),
            activeUsers7d=active_row[0],
            registrations=[
                RegistrationCount(month=r["m"], count=r["n"])
                for r in c.execute(
                    "SELECT substr(created_at, 1, 7) AS m, COUNT(*) AS n FROM users"
                    " GROUP BY m ORDER BY m"
                )
            ],
        )
    finally:
        c.close()


@router.get("/users")
def list_users(
    admin: Annotated[AdminContext, Depends(admin_user)],
) -> list[AdminUserSummary]:
    c = conn()
    try:
        connections = {}
        for r in c.execute(
            "SELECT user_id, status, last_sync, last_error FROM bank_connections ORDER BY id"
        ):
            connections[r["user_id"]] = AdminConnectionSummary(
                status=r["status"], lastSync=r["last_sync"], lastError=r["last_error"]
            )
        return [
            AdminUserSummary(
                id=r["id"],
                email=r["email"],
                createdAt=r["created_at"],
                lastLogin=r["last_login"],
                isAdmin=bool(r["is_admin"]),
                accounts=r["accounts"],
                transactions=r["transactions"],
                lastTransaction=r["last_tx"],
                budgets=r["budgets"],
                connection=connections.get(r["id"]),
            )
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
def user_detail(
    uid: int, admin: Annotated[AdminContext, Depends(admin_user)]
) -> UserDetailResponse:
    c = conn()
    try:
        row = c.execute(
            "SELECT id, email, created_at, is_admin, last_login, default_account_id"
            " FROM users WHERE id=?",
            (uid,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "unknown user")
        return UserDetailResponse(
            user=serialize_user(UserRecord.from_row(row)),
            accounts=[
                AdminAccountSummary(
                    id=r["id"],
                    name=r["name"],
                    type=r["type"],
                    currency=r["currency"],
                    archived=bool(r["archived"]),
                    balance=r["balance"],
                    transactions=r["tx_count"],
                )
                for r in c.execute(
                    "SELECT a.id, a.name, a.type, a.currency, a.archived,"
                    " a.opening_balance + COALESCE(SUM(CASE WHEN t.category_id IS NOT NULL"
                    "   OR t.transfer_id IS NOT NULL OR t.source IN ('transfer', 'adjustment')"
                    "   THEN t.amount END), 0) AS balance,"
                    " COUNT(t.id) AS tx_count"
                    " FROM accounts a LEFT JOIN transactions t ON t.account_id = a.id"
                    " WHERE a.user_id=? GROUP BY a.id ORDER BY a.sort, a.id",
                    (uid,),
                )
            ],
            recentTransactions=[
                AdminTransactionSummary(
                    id=r["id"],
                    date=r["date"],
                    amount=r["amount"],
                    description=r["description"],
                    account=r["account_name"],
                    category=r["category_name"],
                )
                for r in c.execute(
                    "SELECT t.id, t.date, t.amount, t.description,"
                    " a.name AS account_name, cat.name AS category_name"
                    " FROM transactions t JOIN accounts a ON a.id = t.account_id"
                    " LEFT JOIN categories cat ON cat.id = t.category_id"
                    " WHERE a.user_id=? ORDER BY t.date DESC, t.id DESC LIMIT ?",
                    (uid, RECENT_TX_LIMIT),
                )
            ],
            featureUsage=[
                FeatureCount(feature=r["feature"], count=r["n"])
                for r in c.execute(
                    "SELECT feature, SUM(count) AS n FROM feature_usage WHERE user_id=?"
                    " GROUP BY feature ORDER BY n DESC",
                    (uid,),
                )
            ],
            recentLogins=[
                r["created_at"]
                for r in c.execute(
                    "SELECT created_at FROM activity_events WHERE user_id=? AND kind='login'"
                    " ORDER BY id DESC LIMIT ?",
                    (uid, RECENT_LOGINS_LIMIT),
                )
            ],
        )
    finally:
        c.close()


@router.get("/users/{uid}/transactions")
def user_transactions(
    uid: int,
    admin: Annotated[AdminContext, Depends(admin_user)],
    limit: Annotated[int, Query(ge=1, le=TX_PAGE_MAX)] = TX_PAGE_MAX,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminTransactionDetail]:
    """
    A user's transactions, newest first — the full list behind the detail view's
    preview, rendered as one JSON object per line by the client. Paged (capped at
    ``TX_PAGE_MAX`` rows) so a heavy history can't materialize one giant response;
    the client walks ``offset`` until a short page comes back.
    """
    c = conn()
    try:
        if c.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone() is None:
            raise HTTPException(404, "unknown user")
        return [
            AdminTransactionDetail(
                id=r["id"],
                date=r["date"],
                amount=r["amount"],
                description=r["description"],
                account=r["account_name"],
                category=r["category_name"],
                mcc=r["mcc"],
                comment=r["comment"],
                source=r["source"],
            )
            for r in c.execute(
                "SELECT t.id, t.date, t.amount, t.description, t.mcc, t.comment, t.source,"
                " a.name AS account_name, cat.name AS category_name"
                " FROM transactions t JOIN accounts a ON a.id = t.account_id"
                " LEFT JOIN categories cat ON cat.id = t.category_id"
                " WHERE a.user_id=? ORDER BY t.date DESC, t.id DESC"
                " LIMIT ? OFFSET ?",
                (uid, limit, offset),
            )
        ]
    finally:
        c.close()


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class DeleteTransactionsBody:
    ids: list[int]


@router.post("/users/{uid}/transactions/delete")
def delete_user_transactions(
    uid: int,
    body: DeleteTransactionsBody,
    admin: Annotated[AdminContext, Depends(admin_user)],
) -> dict[str, int]:
    """
    Bulk-delete a selection of one user's transactions. All-or-nothing: every
    id must belong to the target user, otherwise nothing is deleted — a stale
    selection must fail loudly rather than remove half of it.
    """
    ids = sorted(set(body.ids))
    if not ids:
        raise HTTPException(400, "no transaction ids given")
    c = conn()
    try:
        if c.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone() is None:
            raise HTTPException(404, "unknown user")
        # the delete itself is scoped to the user's accounts and its rowcount
        # verified, so there is no check-then-delete window: an id that stopped
        # belonging to this user mid-flight rolls the whole batch back
        deleted = 0
        for i in range(0, len(ids), SQL_CHUNK):
            chunk = ids[i : i + SQL_CHUNK]
            marks = ",".join("?" * len(chunk))
            # the interpolation only builds "?" placeholders; values are bound
            cur = c.execute(
                f"DELETE FROM transactions WHERE id IN ({marks})"  # nosec B608
                " AND account_id IN (SELECT id FROM accounts WHERE user_id=?)",
                (*chunk, uid),
            )
            deleted += cur.rowcount
        if deleted != len(ids):
            c.rollback()
            raise HTTPException(400, "some transactions do not belong to this user")
        c.commit()
        return {"deleted": deleted}
    finally:
        c.close()


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class CreateUserBody:
    email: str
    password: str


@router.post("/users")
def create_user_admin(
    body: CreateUserBody, admin: Annotated[AdminContext, Depends(admin_user)]
) -> UserResponse:
    c = conn()
    try:
        return create_user(c, body.email, body.password)
    finally:
        c.close()


@router.delete("/users/{uid}")
def delete_user(uid: int, admin: Annotated[AdminContext, Depends(admin_user)]) -> dict[str, bool]:
    if uid == admin.id:
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
def activity(admin: Annotated[AdminContext, Depends(admin_user)]) -> ActivityResponse:
    c = conn()
    try:
        day_cutoff = _cutoff(ACTIVITY_WINDOW_DAYS)[:10]
        return ActivityResponse(
            features=[
                FeatureCount(feature=r["feature"], count=r["n"])
                for r in c.execute(
                    "SELECT feature, SUM(count) AS n FROM feature_usage WHERE day >= ?"
                    " GROUP BY feature ORDER BY n DESC",
                    (day_cutoff,),
                )
            ],
            daily=[
                DayCount(day=r["day"], count=r["n"])
                for r in c.execute(
                    "SELECT day, SUM(count) AS n FROM feature_usage WHERE day >= ?"
                    " GROUP BY day ORDER BY day",
                    (day_cutoff,),
                )
            ],
            recentLogins=[
                LoginEvent(email=r["email"], at=r["created_at"])
                for r in c.execute(
                    "SELECT u.email, e.created_at FROM activity_events e"
                    " JOIN users u ON u.id = e.user_id WHERE e.kind='login'"
                    " ORDER BY e.id DESC LIMIT ?",
                    (RECENT_LOGINS_LIMIT,),
                )
            ],
        )
    finally:
        c.close()
