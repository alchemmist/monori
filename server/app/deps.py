import sqlite3
from collections.abc import Iterable, Mapping
from itertools import batched
from typing import TypedDict, cast

from . import db as dbmod
from .transfer_service import list_transfers

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


type SqliteValue = bytes | float | int | str | None


def _account_int(value: SqliteValue) -> int:
    if isinstance(value, int):
        return value
    raise TypeError("account field must be an integer")


def _account_str(value: SqliteValue) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("account field must be a string")


def _account_optional_int(value: SqliteValue) -> int | None:
    return None if value is None else _account_int(value)


def _account_optional_str(value: SqliteValue) -> str | None:
    return None if value is None else _account_str(value)


def conn() -> sqlite3.Connection:
    return dbmod.connect()


def serialize_group(r: Mapping[str, object]) -> dict[str, object]:
    return {"id": r["id"], "name": r["name"], "sort": r["sort"], "kind": r["kind"]}


def serialize_category(r: Mapping[str, object]) -> dict[str, object]:
    keys = r.keys()
    return {
        "id": r["id"],
        "groupId": r["group_id"],
        "name": r["name"],
        "keywords": r["keywords"],
        "sort": r["sort"],
        "archived": bool(r["archived"]),
        "goalTarget": r["goal_target"] if "goal_target" in keys else None,
        "goalStatus": r["goal_status"] if "goal_status" in keys else None,
        "goalTargetDate": r["goal_target_date"] if "goal_target_date" in keys else None,
    }


def serialize_account(r: Mapping[str, SqliteValue]) -> AccountResponse:
    card_tails = str(r["card_tails"] or "")
    return {
        "id": _account_int(r["id"]),
        "name": _account_str(r["name"]),
        "type": _account_str(r["type"]),
        "icon": _account_str(r["icon"]),
        "color": _account_str(r["color"]),
        "iconImage": _account_optional_str(r["icon_image"]),
        "currency": _account_str(r["currency"]),
        "sort": _account_int(r["sort"]),
        "archived": bool(r["archived"]),
        "openingBalance": _account_int(r["opening_balance"]),
        "openingDate": _account_optional_str(r["opening_date"]),
        "connectionId": _account_optional_int(r["connection_id"]),
        "bankRef": _account_str(r["bank_ref"]),
        "cardTails": [t for t in card_tails.split(",") if t],
    }


def serialize_tx(
    r: Mapping[str, object], splits: Iterable[Mapping[str, object]] = ()
) -> dict[str, object]:
    return {
        "id": r["id"],
        "date": r["date"],
        "amount": r["amount"],
        "description": r["description"],
        "bankCategory": r["bank_category"],
        "mcc": r["mcc"],
        "categoryId": r["category_id"],
        "accountId": r["account_id"],
        "transferId": r["transfer_id"],
        "comment": r["comment"],
        "source": r["source"],
        "hidden": bool(r["hidden"]),
        "splits": [
            {
                "id": split["id"],
                "categoryId": split["category_id"],
                "amount": split["amount"],
                "comment": split["comment"],
            }
            for split in splits
        ],
    }


def serialize_transactions(
    cur: sqlite3.Cursor, rows: Iterable[Mapping[str, object]]
) -> list[dict[str, object]]:
    rows = list(rows)
    if not rows:
        return []
    ids = [cast("int", row["id"]) for row in rows]
    by_tx: dict[int, list[Mapping[str, object]]] = {}
    for chunk in batched(ids, SPLIT_FETCH_BATCH_SIZE):
        marks = ",".join("?" for _ in chunk)
        for split in cur.execute(
            # `marks` contains generated positional placeholders, never user input.
            f"SELECT id, transaction_id, category_id, amount, comment"  # nosec B608
            f" FROM splits WHERE transaction_id IN ({marks})"
            " ORDER BY transaction_id, sort, id",
            chunk,
        ):
            by_tx.setdefault(cast("int", split["transaction_id"]), []).append(split)
    return [serialize_tx(row, by_tx.get(cast("int", row["id"]), ())) for row in rows]


def serialize_user(r: Mapping[str, object]) -> dict[str, object]:
    """
    A user, without the password hash.
    """
    return {
        "id": r["id"],
        "email": r["email"],
        "createdAt": r["created_at"],
        "isAdmin": bool(r["is_admin"]),
        "lastLogin": r["last_login"],
        "defaultAccountId": r["default_account_id"],
    }


def serialize_connection(r: Mapping[str, object]) -> dict[str, object]:
    """
    A bank connection, without any secret material (credentials/session).
    """
    return {
        "id": r["id"],
        "bank": r["bank"],
        "kind": r["kind"],
        "status": r["status"],
        "lastSync": r["last_sync"],
        "lastError": r["last_error"],
        "hasCredentials": r["credentials_encrypted"] is not None,
        "createdAt": r["created_at"],
        "updatedAt": r["updated_at"],
    }


def serialize_budget(r: Mapping[str, object]) -> dict[str, object]:
    return {
        "categoryId": r["category_id"],
        "year": r["year"],
        "month": r["month"],
        "amount": r["amount"],
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
) -> list[dict[str, object]]:
    """
    The newest ``tx_limit`` transactions, handed back in the canonical
    ``date, id`` order the client keeps them in. ``None`` means all of them.
    """
    if tx_limit is None:
        return serialize_transactions(cur, cur.execute(f"{TX_COLUMNS} ORDER BY t.date, t.id", uid))
    rows = cur.execute(f"{TX_COLUMNS} ORDER BY t.date DESC, t.id DESC LIMIT ?", (*uid, tx_limit))
    return serialize_transactions(cur, reversed(list(rows)))


def snapshot(c: sqlite3.Connection, user_id: int, tx_limit: int | None = None) -> dict[str, object]:
    cur = c.cursor()
    uid = (user_id,)
    transactions = _snapshot_transactions(cur, uid, tx_limit)
    # a short read means the window covered everything, so the count is free
    transactions_total = (
        len(transactions)
        if tx_limit is None or len(transactions) < tx_limit
        else cur.execute(
            "SELECT COUNT(*) FROM transactions t JOIN accounts a ON a.id = t.account_id"
            " WHERE a.user_id=? AND t.hidden = 0",
            uid,
        ).fetchone()[0]
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
