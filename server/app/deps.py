"""Provide backend functionality."""

import json
import sqlite3
from collections.abc import Iterable
from itertools import batched

from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass as pydantic_dataclass

from . import db as dbmod
from .db_records import (
    AccountRecord,
    BudgetRecord,
    CategoryRecord,
    ConnectionRecord,
    GroupRecord,
    SplitRecord,
    TransactionRecord,
    UserRecord,
)
from .transfer_service import TransferResponse, list_transfers

SPLIT_FETCH_BATCH_SIZE = 500


_DTO_CONFIG = ConfigDict(extra="forbid", populate_by_name=True)


@pydantic_dataclass(config=_DTO_CONFIG)
class AccountResponse:
    """Represent AccountResponse."""

    id: int
    name: str
    type: str
    icon: str
    color: str
    currency: str
    sort: int
    archived: bool
    icon_image: str | None = Field(
        ..., serialization_alias="iconImage", validation_alias="iconImage"
    )
    opening_balance: int = Field(
        ..., serialization_alias="openingBalance", validation_alias="openingBalance"
    )
    opening_date: str | None = Field(
        ..., serialization_alias="openingDate", validation_alias="openingDate"
    )
    connection_id: int | None = Field(
        ..., serialization_alias="connectionId", validation_alias="connectionId"
    )
    bank_ref: str = Field(..., serialization_alias="bankRef", validation_alias="bankRef")
    card_tails: list[str] = Field(
        ..., serialization_alias="cardTails", validation_alias="cardTails"
    )


@pydantic_dataclass(config=_DTO_CONFIG)
class GroupResponse:
    """Represent GroupResponse."""

    id: int
    name: str
    sort: int
    kind: str


@pydantic_dataclass(config=_DTO_CONFIG)
class CategoryResponse:
    """Represent CategoryResponse."""

    id: int
    name: str
    keywords: str
    sort: int
    archived: bool
    group_id: int = Field(..., serialization_alias="groupId", validation_alias="groupId")
    goal_target: int | None = Field(
        ..., serialization_alias="goalTarget", validation_alias="goalTarget"
    )
    goal_status: str | None = Field(
        ..., serialization_alias="goalStatus", validation_alias="goalStatus"
    )
    goal_target_date: str | None = Field(
        ..., serialization_alias="goalTargetDate", validation_alias="goalTargetDate"
    )


@pydantic_dataclass(config=_DTO_CONFIG)
class SplitResponse:
    """Represent SplitResponse."""

    id: int
    amount: int
    comment: str
    category_id: int = Field(..., serialization_alias="categoryId", validation_alias="categoryId")


@pydantic_dataclass(config=_DTO_CONFIG)
class TransactionResponse:
    """Represent TransactionResponse."""

    id: int
    date: str
    amount: int
    description: str
    mcc: str
    comment: str
    source: str
    hidden: bool
    splits: list[SplitResponse]
    bank_category: str = Field(
        ..., serialization_alias="bankCategory", validation_alias="bankCategory"
    )
    category_id: int | None = Field(
        ..., serialization_alias="categoryId", validation_alias="categoryId"
    )
    account_id: int = Field(..., serialization_alias="accountId", validation_alias="accountId")
    transfer_id: str | None = Field(
        ..., serialization_alias="transferId", validation_alias="transferId"
    )


@pydantic_dataclass(config=_DTO_CONFIG)
class UserResponse:
    """Represent UserResponse."""

    id: int
    email: str
    created_at: str = Field(..., serialization_alias="createdAt", validation_alias="createdAt")
    is_admin: bool = Field(..., serialization_alias="isAdmin", validation_alias="isAdmin")
    last_login: str | None = Field(
        ..., serialization_alias="lastLogin", validation_alias="lastLogin"
    )
    default_account_id: int | None = Field(
        ..., serialization_alias="defaultAccountId", validation_alias="defaultAccountId"
    )


@pydantic_dataclass(config=_DTO_CONFIG)
class ConnectionResponse:
    """Represent ConnectionResponse."""

    id: int
    bank: str
    kind: str
    status: str
    last_sync: str | None = Field(..., serialization_alias="lastSync", validation_alias="lastSync")
    last_error: str | None = Field(
        ..., serialization_alias="lastError", validation_alias="lastError"
    )
    has_credentials: bool = Field(
        ..., serialization_alias="hasCredentials", validation_alias="hasCredentials"
    )
    created_at: str = Field(..., serialization_alias="createdAt", validation_alias="createdAt")
    updated_at: str = Field(..., serialization_alias="updatedAt", validation_alias="updatedAt")


@pydantic_dataclass(config=_DTO_CONFIG)
class BudgetResponse:
    """Represent BudgetResponse."""

    year: int
    month: int
    amount: int
    category_id: int = Field(..., serialization_alias="categoryId", validation_alias="categoryId")


@pydantic_dataclass(config=_DTO_CONFIG)
class IdResponse:
    """Represent IdResponse."""

    id: int | None


@pydantic_dataclass(config=_DTO_CONFIG)
class SnapshotResponse:
    """Represent SnapshotResponse."""

    accounts: list[AccountResponse]
    groups: list[GroupResponse]
    categories: list[CategoryResponse]
    transactions: list[TransactionResponse]
    transfers: list["TransferResponse"]
    budgets: list[BudgetResponse]
    connections: list[ConnectionResponse]
    transactions_total: int = Field(
        ..., serialization_alias="transactionsTotal", validation_alias="transactionsTotal"
    )


def conn() -> sqlite3.Connection:
    """Handle conn."""
    return dbmod.connect()


def serialize_group(group: GroupRecord) -> GroupResponse:
    """Handle serialize group."""
    return GroupResponse(id=group.id, name=group.name, sort=group.sort, kind=group.kind)


def serialize_category(category: CategoryRecord) -> CategoryResponse:
    """Handle serialize category."""
    return CategoryResponse(
        id=category.id,
        group_id=category.group_id,
        name=category.name,
        keywords=category.keywords,
        sort=category.sort,
        archived=category.archived,
        goal_target=category.goal_target,
        goal_status=category.goal_status,
        goal_target_date=category.goal_target_date,
    )


def serialize_account(account: AccountRecord) -> AccountResponse:
    """Handle serialize account."""
    return AccountResponse(
        id=account.id,
        name=account.name,
        type=account.type,
        icon=account.icon,
        color=account.color,
        icon_image=account.icon_image,
        currency=account.currency,
        sort=account.sort,
        archived=account.archived,
        opening_balance=account.opening_balance,
        opening_date=account.opening_date,
        connection_id=account.connection_id,
        bank_ref=account.bank_ref,
        card_tails=[tail for tail in account.card_tails.split(",") if tail],
    )


def serialize_tx(
    transaction: TransactionRecord,
    splits: Iterable[SplitRecord] = (),
) -> TransactionResponse:
    """Handle serialize tx."""
    return TransactionResponse(
        id=transaction.id,
        date=transaction.date,
        amount=transaction.amount,
        description=transaction.description,
        bank_category=transaction.bank_category,
        mcc=transaction.mcc,
        category_id=transaction.category_id,
        account_id=transaction.account_id,
        transfer_id=transaction.transfer_id,
        comment=transaction.comment,
        source=transaction.source,
        hidden=transaction.hidden,
        splits=[
            SplitResponse(
                id=split.id,
                category_id=split.category_id,
                amount=split.amount,
                comment=split.comment,
            )
            for split in splits
        ],
    )


def serialize_transactions(
    cur: sqlite3.Cursor,
    rows: Iterable[sqlite3.Row],
) -> list[TransactionResponse]:
    """Handle serialize transactions."""
    transactions = [TransactionRecord.from_row(row) for row in rows]
    if not transactions:
        return []
    ids = [transaction.id for transaction in transactions]
    by_tx: dict[int, list[SplitRecord]] = {}
    for chunk in batched(ids, SPLIT_FETCH_BATCH_SIZE):
        for split in cur.execute(
            "SELECT id, transaction_id, category_id, amount, comment"
            " FROM splits WHERE transaction_id IN (SELECT value FROM json_each(?))"
            " ORDER BY transaction_id, sort, id",
            (json.dumps(chunk),),
        ):
            record = SplitRecord.from_row(split)
            by_tx.setdefault(record.transaction_id, []).append(record)
    return [serialize_tx(tx, by_tx.get(tx.id, ())) for tx in transactions]


def serialize_user(user: UserRecord) -> UserResponse:
    """Handle A user, without the password hash."""
    return UserResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        is_admin=user.is_admin,
        last_login=user.last_login,
        default_account_id=user.default_account_id,
    )


def serialize_connection(connection: ConnectionRecord) -> ConnectionResponse:
    """Handle A bank connection, without any secret material (credentials/session)."""
    return ConnectionResponse(
        id=connection.id,
        bank=connection.bank,
        kind=connection.kind,
        status=connection.status,
        last_sync=connection.last_sync,
        last_error=connection.last_error,
        has_credentials=connection.has_credentials,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def serialize_budget(budget: BudgetRecord) -> BudgetResponse:
    """Handle serialize budget."""
    return BudgetResponse(
        category_id=budget.category_id,
        year=budget.year,
        month=budget.month,
        amount=budget.amount,
    )


LIGHT_SNAPSHOT_TX_LIMIT = 500

TX_COLUMNS = (
    "SELECT t.id, t.date, t.amount, t.description, t.bank_category, t.mcc,"
    " t.category_id, t.account_id, t.transfer_id, t.comment, t.source, t.hidden"
    " FROM transactions t JOIN accounts a ON a.id = t.account_id"
    " WHERE a.user_id=? AND t.hidden = 0"
)


def _snapshot_transactions(
    cur: sqlite3.Cursor,
    uid: tuple[int],
    tx_limit: int | None,
) -> list[TransactionResponse]:
    """
    Handle The newest ``tx_limit`` transactions, handed back in the canonical.

    ``date, id`` order the client keeps them in. ``None`` means all of them.
    """
    if tx_limit is None:
        return serialize_transactions(cur, cur.execute(f"{TX_COLUMNS} ORDER BY t.date, t.id", uid))
    rows = cur.execute(f"{TX_COLUMNS} ORDER BY t.date DESC, t.id DESC LIMIT ?", (*uid, tx_limit))
    return serialize_transactions(cur, reversed(list(rows)))


def snapshot(c: sqlite3.Connection, user_id: int, tx_limit: int | None = None) -> SnapshotResponse:
    """Handle snapshot."""
    cur = c.cursor()
    uid = (user_id,)
    transactions = _snapshot_transactions(cur, uid, tx_limit)

    transactions_total = (
        len(transactions)
        if tx_limit is None or len(transactions) < tx_limit
        else cur.execute(
            "SELECT COUNT(*) FROM transactions t JOIN accounts a ON a.id = t.account_id"
            " WHERE a.user_id=? AND t.hidden = 0",
            uid,
        ).fetchone()[0]
    )
    return SnapshotResponse(
        accounts=[
            serialize_account(AccountRecord.from_row(r))
            for r in cur.execute(
                "SELECT id, name, type, icon, color, icon_image, currency, sort, archived,"
                " opening_balance, opening_date, connection_id, bank_ref, card_tails"
                " FROM accounts WHERE user_id=? ORDER BY sort, id",
                uid,
            )
        ],
        groups=[
            serialize_group(GroupRecord.from_row(r))
            for r in cur.execute(
                "SELECT g.id, g.name, g.sort, t.type AS kind FROM category_groups g"
                " JOIN category_group_types t ON t.id=g.type_id WHERE g.user_id=?"
                " ORDER BY g.sort, g.id",
                uid,
            )
        ],
        categories=[
            serialize_category(CategoryRecord.from_row(r))
            for r in cur.execute(
                "SELECT c.id, c.group_id, c.name, c.keywords, c.sort, c.archived,"
                " c.goal_target, c.goal_status, c.goal_target_date"
                " FROM categories c JOIN category_groups g ON g.id = c.group_id"
                " WHERE g.user_id=? ORDER BY c.sort, c.id",
                uid,
            )
        ],
        transactions=transactions,
        transactions_total=transactions_total,
        transfers=list_transfers(c, user_id),
        budgets=[
            serialize_budget(BudgetRecord.from_row(r))
            for r in cur.execute(
                "SELECT b.category_id, b.year, b.month, b.amount FROM budgets b"
                " JOIN categories c ON c.id = b.category_id"
                " JOIN category_groups g ON g.id = c.group_id"
                " WHERE g.user_id=? ORDER BY b.year, b.month, b.category_id",
                uid,
            )
        ],
        connections=[
            serialize_connection(ConnectionRecord.from_row(r))
            for r in cur.execute(
                "SELECT bc.id, bc.bank, bc.kind, bc.status, bc.last_sync,"
                " bc.last_error, bc.credentials_encrypted, bc.created_at, bc.updated_at"
                " FROM bank_connections bc WHERE bc.user_id=? ORDER BY bc.id",
                uid,
            )
        ],
    )
