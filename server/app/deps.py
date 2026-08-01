import sqlite3
from collections.abc import Iterable, Mapping
from itertools import batched
from typing import TypedDict

from . import db as dbmod
from .transfer_service import TransferResponse, list_transfers
from .value_types import (
    SqliteValue,
    sqlite_int,
    sqlite_optional_int,
    sqlite_optional_str,
    sqlite_str,
)

SPLIT_FETCH_BATCH_SIZE = 500


class AccountResponse(TypedDict):
    id: int
    name: str
    type: str
    icon: str
    color: str
    iconImage: str | None
    currency: str
    sort: int
    archived: bool
    openingBalance: int
    openingDate: str | None
    connectionId: int | None
    bankRef: str
    cardTails: list[str]


class GroupResponse(TypedDict):
    id: int
    name: str
    sort: int
    kind: str


class CategoryResponse(TypedDict):
    id: int
    groupId: int
    name: str
    keywords: str
    sort: int
    archived: bool
    goalTarget: int | None
    goalStatus: str | None
    goalTargetDate: str | None


class SplitResponse(TypedDict):
    id: int
    categoryId: int
    amount: int
    comment: str


class TransactionResponse(TypedDict):
    id: int
    date: str
    amount: int
    description: str
    bankCategory: str
    mcc: str
    categoryId: int | None
    accountId: int
    transferId: str | None
    comment: str
    source: str
    hidden: bool
    splits: list[SplitResponse]


class UserResponse(TypedDict):
    id: int
    email: str
    createdAt: str
    isAdmin: bool
    lastLogin: str | None
    defaultAccountId: int | None


class ConnectionResponse(TypedDict):
    id: int
    bank: str
    kind: str
    status: str
    lastSync: str | None
    lastError: str | None
    hasCredentials: bool
    createdAt: str
    updatedAt: str


class BudgetResponse(TypedDict):
    categoryId: int
    year: int
    month: int
    amount: int


class SnapshotResponse(TypedDict):
    accounts: list[AccountResponse]
    groups: list[GroupResponse]
    categories: list[CategoryResponse]
    transactions: list[TransactionResponse]
    transactionsTotal: int
    transfers: list[TransferResponse]
    budgets: list[BudgetResponse]
    connections: list[ConnectionResponse]


def conn() -> sqlite3.Connection:
    return dbmod.connect()


def serialize_group(r: Mapping[str, SqliteValue]) -> GroupResponse:
    return {
        "id": sqlite_int(r["id"]),
        "name": sqlite_str(r["name"]),
        "sort": sqlite_int(r["sort"]),
        "kind": sqlite_str(r["kind"]),
    }


def serialize_category(r: Mapping[str, SqliteValue]) -> CategoryResponse:
    keys = r.keys()
    return {
        "id": sqlite_int(r["id"]),
        "groupId": sqlite_int(r["group_id"]),
        "name": sqlite_str(r["name"]),
        "keywords": sqlite_str(r["keywords"]),
        "sort": sqlite_int(r["sort"]),
        "archived": bool(r["archived"]),
        "goalTarget": sqlite_optional_int(r["goal_target"]) if "goal_target" in keys else None,
        "goalStatus": sqlite_optional_str(r["goal_status"]) if "goal_status" in keys else None,
        "goalTargetDate": (
            sqlite_optional_str(r["goal_target_date"]) if "goal_target_date" in keys else None
        ),
    }


def serialize_account(r: Mapping[str, SqliteValue]) -> AccountResponse:
    card_tails = str(r["card_tails"] or "")
    return {
        "id": sqlite_int(r["id"]),
        "name": sqlite_str(r["name"]),
        "type": sqlite_str(r["type"]),
        "icon": sqlite_str(r["icon"]),
        "color": sqlite_str(r["color"]),
        "iconImage": sqlite_optional_str(r["icon_image"]),
        "currency": sqlite_str(r["currency"]),
        "sort": sqlite_int(r["sort"]),
        "archived": bool(r["archived"]),
        "openingBalance": sqlite_int(r["opening_balance"]),
        "openingDate": sqlite_optional_str(r["opening_date"]),
        "connectionId": sqlite_optional_int(r["connection_id"]),
        "bankRef": sqlite_str(r["bank_ref"]),
        "cardTails": [t for t in card_tails.split(",") if t],
    }


def serialize_tx(
    r: Mapping[str, SqliteValue], splits: Iterable[Mapping[str, SqliteValue]] = ()
) -> TransactionResponse:
    return {
        "id": sqlite_int(r["id"]),
        "date": sqlite_str(r["date"]),
        "amount": sqlite_int(r["amount"]),
        "description": sqlite_str(r["description"]),
        "bankCategory": sqlite_str(r["bank_category"]),
        "mcc": sqlite_str(r["mcc"]),
        "categoryId": sqlite_optional_int(r["category_id"]),
        "accountId": sqlite_int(r["account_id"]),
        "transferId": sqlite_optional_str(r["transfer_id"]),
        "comment": sqlite_str(r["comment"]),
        "source": sqlite_str(r["source"]),
        "hidden": bool(r["hidden"]),
        "splits": [
            {
                "id": sqlite_int(split["id"]),
                "categoryId": sqlite_int(split["category_id"]),
                "amount": sqlite_int(split["amount"]),
                "comment": sqlite_str(split["comment"]),
            }
            for split in splits
        ],
    }


def serialize_transactions(
    cur: sqlite3.Cursor, rows: Iterable[Mapping[str, SqliteValue]]
) -> list[TransactionResponse]:
    rows = list(rows)
    if not rows:
        return []
    ids = [sqlite_int(row["id"]) for row in rows]
    by_tx: dict[int, list[Mapping[str, SqliteValue]]] = {}
    for chunk in batched(ids, SPLIT_FETCH_BATCH_SIZE):
        marks = ",".join("?" for _ in chunk)
        for split in cur.execute(
            # `marks` contains generated positional placeholders, never user input.
            f"SELECT id, transaction_id, category_id, amount, comment"  # nosec B608
            f" FROM splits WHERE transaction_id IN ({marks})"
            " ORDER BY transaction_id, sort, id",
            chunk,
        ):
            by_tx.setdefault(sqlite_int(split["transaction_id"]), []).append(split)
    return [serialize_tx(row, by_tx.get(sqlite_int(row["id"]), ())) for row in rows]


def serialize_user(r: Mapping[str, SqliteValue]) -> UserResponse:
    """
    A user, without the password hash.
    """
    return {
        "id": sqlite_int(r["id"]),
        "email": sqlite_str(r["email"]),
        "createdAt": sqlite_str(r["created_at"]),
        "isAdmin": bool(r["is_admin"]),
        "lastLogin": sqlite_optional_str(r["last_login"]),
        "defaultAccountId": sqlite_optional_int(r["default_account_id"]),
    }


def serialize_connection(r: Mapping[str, SqliteValue]) -> ConnectionResponse:
    """
    A bank connection, without any secret material (credentials/session).
    """
    return {
        "id": sqlite_int(r["id"]),
        "bank": sqlite_str(r["bank"]),
        "kind": sqlite_str(r["kind"]),
        "status": sqlite_str(r["status"]),
        "lastSync": sqlite_optional_str(r["last_sync"]),
        "lastError": sqlite_optional_str(r["last_error"]),
        "hasCredentials": r["credentials_encrypted"] is not None,
        "createdAt": sqlite_str(r["created_at"]),
        "updatedAt": sqlite_str(r["updated_at"]),
    }


def serialize_budget(r: Mapping[str, SqliteValue]) -> BudgetResponse:
    return {
        "categoryId": sqlite_int(r["category_id"]),
        "year": sqlite_int(r["year"]),
        "month": sqlite_int(r["month"]),
        "amount": sqlite_int(r["amount"]),
    }


LIGHT_SNAPSHOT_TX_LIMIT = 500

TX_COLUMNS = (
    "SELECT t.id, t.date, t.amount, t.description, t.bank_category, t.mcc,"
    " t.category_id, t.account_id, t.transfer_id, t.comment, t.source, t.hidden"
    " FROM transactions t JOIN accounts a ON a.id = t.account_id"
    " WHERE a.user_id=? AND t.hidden = 0"
)


def _snapshot_transactions(
    cur: sqlite3.Cursor, uid: tuple[int], tx_limit: int | None
) -> list[TransactionResponse]:
    """
    The newest ``tx_limit`` transactions, handed back in the canonical
    ``date, id`` order the client keeps them in. ``None`` means all of them.
    """
    if tx_limit is None:
        return serialize_transactions(cur, cur.execute(f"{TX_COLUMNS} ORDER BY t.date, t.id", uid))
    rows = cur.execute(f"{TX_COLUMNS} ORDER BY t.date DESC, t.id DESC LIMIT ?", (*uid, tx_limit))
    return serialize_transactions(cur, reversed(list(rows)))


def snapshot(c: sqlite3.Connection, user_id: int, tx_limit: int | None = None) -> SnapshotResponse:
    cur = c.cursor()
    uid = (user_id,)
    transactions = _snapshot_transactions(cur, uid, tx_limit)
    # a short read means the window covered everything, so the count is free
    transactions_total = (
        len(transactions)
        if tx_limit is None or len(transactions) < tx_limit
        else sqlite_int(
            cur.execute(
                "SELECT COUNT(*) FROM transactions t JOIN accounts a ON a.id = t.account_id"
                " WHERE a.user_id=? AND t.hidden = 0",
                uid,
            ).fetchone()[0]
        )
    )
    return {
        "accounts": [
            serialize_account(r)
            for r in cur.execute(
                "SELECT id, name, type, icon, color, icon_image, currency, sort, archived,"
                " opening_balance, opening_date, connection_id, bank_ref, card_tails"
                " FROM accounts WHERE user_id=? ORDER BY sort, id",
                uid,
            )
        ],
        "groups": [
            serialize_group(r)
            for r in cur.execute(
                "SELECT g.id, g.name, g.sort, t.type AS kind FROM category_groups g"
                " JOIN category_group_types t ON t.id=g.type_id WHERE g.user_id=?"
                " ORDER BY g.sort, g.id",
                uid,
            )
        ],
        "categories": [
            serialize_category(r)
            for r in cur.execute(
                "SELECT c.id, c.group_id, c.name, c.keywords, c.sort, c.archived,"
                " c.goal_target, c.goal_status, c.goal_target_date"
                " FROM categories c JOIN category_groups g ON g.id = c.group_id"
                " WHERE g.user_id=? ORDER BY c.sort, c.id",
                uid,
            )
        ],
        "transactions": transactions,
        "transactionsTotal": transactions_total,
        "transfers": list_transfers(c, user_id),
        "budgets": [
            serialize_budget(r)
            for r in cur.execute(
                "SELECT b.category_id, b.year, b.month, b.amount FROM budgets b"
                " JOIN categories c ON c.id = b.category_id"
                " JOIN category_groups g ON g.id = c.group_id"
                " WHERE g.user_id=? ORDER BY b.year, b.month, b.category_id",
                uid,
            )
        ],
        "connections": [
            serialize_connection(r)
            for r in cur.execute(
                "SELECT bc.id, bc.bank, bc.kind, bc.status, bc.last_sync,"
                " bc.last_error, bc.credentials_encrypted, bc.created_at, bc.updated_at"
                " FROM bank_connections bc WHERE bc.user_id=? ORDER BY bc.id",
                uid,
            )
        ],
    }
