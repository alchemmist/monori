"""Provide backend functionality."""

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from .domain_types import (
    AccountType,
    CategoryGroupKind,
    ConnectionStatus,
    GoalStatus,
    TransactionSource,
)


class RowValueError(ValueError):
    """Raised when a SQLite row does not match the selected record shape."""


class RowTypeError(TypeError):
    """Raised when a SQLite column has an unexpected Python type."""


type SqliteCell = int | float | str | bytes | None


def _row_value(row: sqlite3.Row, key: str) -> SqliteCell:
    try:
        return cast("SqliteCell", row[key])
    except IndexError as error:
        message = f"SQL row is missing required column {key!r}"
        raise RowValueError(message) from error


def row_int(row: sqlite3.Row, key: str) -> int:
    """Read a required SQLite integer without leaking ``Any`` into records."""
    value = _row_value(row, key)
    if type(value) is not int:
        message = f"SQL column {key!r} must be an int, got {type(value).__name__}"
        raise RowTypeError(message)
    return value


def row_str(row: sqlite3.Row, key: str) -> str:
    """Read a required SQLite text column without leaking ``Any`` into records."""
    value = _row_value(row, key)
    if not isinstance(value, str):
        message = f"SQL column {key!r} must be a str, got {type(value).__name__}"
        raise RowTypeError(message)
    return value


def row_optional_int(row: sqlite3.Row, key: str) -> int | None:
    """Read a nullable SQLite integer column."""
    value = _row_value(row, key)
    if value is None:
        return None
    if type(value) is not int:
        message = f"SQL column {key!r} must be an int or null, got {type(value).__name__}"
        raise RowTypeError(message)
    return value


def row_optional_str(row: sqlite3.Row, key: str) -> str | None:
    """Read a nullable SQLite text column."""
    value = _row_value(row, key)
    if value is None:
        return None
    if not isinstance(value, str):
        message = f"SQL column {key!r} must be a str or null, got {type(value).__name__}"
        raise RowTypeError(message)
    return value


def row_bool(row: sqlite3.Row, key: str) -> bool:
    """Read SQLite's integer-backed boolean representation."""
    value = row_int(row, key)
    if value not in (0, 1):
        message = f"SQL column {key!r} must be 0 or 1, got {value}"
        raise RowValueError(message)
    return bool(value)


def row_enum[EnumValue: StrEnum](
    row: sqlite3.Row, key: str, enum_type: type[EnumValue]
) -> EnumValue:
    """Read a closed string value and make unexpected persisted data explicit."""
    try:
        return enum_type(row_str(row, key))
    except ValueError as error:
        message = f"SQL column {key!r} contains an invalid {enum_type.__name__}"
        raise RowValueError(message) from error


@dataclass(frozen=True, slots=True)
class GroupRecord:
    """Represent GroupRecord."""

    id: int
    name: str
    sort: int
    kind: CategoryGroupKind

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "GroupRecord":
        """Handle from row."""
        return cls(
            id=row_int(row, "id"),
            name=row_str(row, "name"),
            sort=row_int(row, "sort"),
            kind=row_enum(row, "kind", CategoryGroupKind),
        )


@dataclass(frozen=True, slots=True)
class CategoryRecord:
    """Represent CategoryRecord."""

    id: int
    group_id: int
    name: str
    keywords: str
    sort: int
    archived: bool
    goal_target: int | None = None
    goal_status: GoalStatus | None = None
    goal_target_date: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "CategoryRecord":
        """Handle from row."""
        keys = row.keys()
        return cls(
            id=row_int(row, "id"),
            group_id=row_int(row, "group_id"),
            name=row_str(row, "name"),
            keywords=row_str(row, "keywords"),
            sort=row_int(row, "sort"),
            archived=row_bool(row, "archived"),
            goal_target=row_optional_int(row, "goal_target") if "goal_target" in keys else None,
            goal_status=(
                row_enum(row, "goal_status", GoalStatus)
                if "goal_status" in keys and row_optional_str(row, "goal_status") is not None
                else None
            ),
            goal_target_date=(
                row_optional_str(row, "goal_target_date") if "goal_target_date" in keys else None
            ),
        )


@dataclass(frozen=True, slots=True)
class CategoryOwnershipRecord:
    """Represent CategoryOwnershipRecord."""

    id: int
    keywords: str
    goal_target: int | None
    type: CategoryGroupKind
    is_goal: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "CategoryOwnershipRecord":
        """Handle from row."""
        return cls(
            id=row_int(row, "id"),
            keywords=row_str(row, "keywords"),
            goal_target=row_optional_int(row, "goal_target"),
            type=row_enum(row, "type", CategoryGroupKind),
            is_goal=row_bool(row, "is_goal"),
        )


@dataclass(frozen=True, slots=True)
class GoalGroupRecord:
    """Represent GoalGroupRecord."""

    id: int
    is_goal: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "GoalGroupRecord":
        """Handle from row."""
        return cls(id=row_int(row, "id"), is_goal=row_bool(row, "is_goal"))


@dataclass(frozen=True, slots=True)
class CategorySignRecord:
    """Represent CategorySignRecord."""

    id: int
    transaction_sign: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "CategorySignRecord":
        """Handle from row."""
        return cls(id=row_int(row, "id"), transaction_sign=row_int(row, "transaction_sign"))


@dataclass(frozen=True, slots=True)
class AccountRecord:
    """Represent AccountRecord."""

    id: int
    name: str
    type: AccountType
    icon: str
    color: str
    icon_image: str | None
    currency: str
    sort: int
    archived: bool
    opening_balance: int
    opening_date: str | None
    connection_id: int | None
    bank_ref: str
    card_tails: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "AccountRecord":
        """Handle from row."""
        return cls(
            id=row_int(row, "id"),
            name=row_str(row, "name"),
            type=row_enum(row, "type", AccountType),
            icon=row_str(row, "icon"),
            color=row_str(row, "color"),
            icon_image=row_optional_str(row, "icon_image"),
            currency=row_str(row, "currency"),
            sort=row_int(row, "sort"),
            archived=row_bool(row, "archived"),
            opening_balance=row_int(row, "opening_balance"),
            opening_date=row_optional_str(row, "opening_date"),
            connection_id=row_optional_int(row, "connection_id"),
            bank_ref=row_str(row, "bank_ref"),
            card_tails=row_str(row, "card_tails"),
        )


@dataclass(frozen=True, slots=True)
class SplitRecord:
    """Represent SplitRecord."""

    id: int
    transaction_id: int
    category_id: int
    amount: int
    comment: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "SplitRecord":
        """Handle from row."""
        return cls(
            id=row_int(row, "id"),
            transaction_id=row_int(row, "transaction_id"),
            category_id=row_int(row, "category_id"),
            amount=row_int(row, "amount"),
            comment=row_str(row, "comment"),
        )


@dataclass(frozen=True, slots=True)
class TransactionRecord:
    """Represent TransactionRecord."""

    id: int
    date: str
    amount: int
    description: str
    bank_category: str
    mcc: str
    category_id: int | None
    account_id: int
    transfer_id: str | None
    comment: str
    source: TransactionSource
    hidden: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TransactionRecord":
        """Handle from row."""
        return cls(
            id=row_int(row, "id"),
            date=row_str(row, "date"),
            amount=row_int(row, "amount"),
            description=row_str(row, "description"),
            bank_category=row_str(row, "bank_category"),
            mcc=row_str(row, "mcc"),
            category_id=row_optional_int(row, "category_id"),
            account_id=row_int(row, "account_id"),
            transfer_id=row_optional_str(row, "transfer_id"),
            comment=row_str(row, "comment"),
            source=row_enum(row, "source", TransactionSource),
            hidden=row_bool(row, "hidden"),
        )


@dataclass(frozen=True, slots=True)
class UserRecord:
    """Represent UserRecord."""

    id: int
    email: str
    created_at: str
    is_admin: bool
    last_login: str | None
    default_account_id: int | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "UserRecord":
        """Handle from row."""
        return cls(
            id=row_int(row, "id"),
            email=row_str(row, "email"),
            created_at=row_str(row, "created_at"),
            is_admin=row_bool(row, "is_admin"),
            last_login=row_optional_str(row, "last_login"),
            default_account_id=row_optional_int(row, "default_account_id"),
        )


@dataclass(frozen=True, slots=True)
class ConnectionRecord:
    """Represent ConnectionRecord."""

    id: int
    bank: str
    kind: str
    status: ConnectionStatus
    last_sync: str | None
    last_error: str | None
    has_credentials: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ConnectionRecord":
        """Handle from row."""
        return cls(
            id=row_int(row, "id"),
            bank=row_str(row, "bank"),
            kind=row_str(row, "kind"),
            status=row_enum(row, "status", ConnectionStatus),
            last_sync=row_optional_str(row, "last_sync"),
            last_error=row_optional_str(row, "last_error"),
            has_credentials=_row_value(row, "credentials_encrypted") is not None,
            created_at=row_str(row, "created_at"),
            updated_at=row_str(row, "updated_at"),
        )


@dataclass(frozen=True, slots=True)
class BudgetRecord:
    """Represent BudgetRecord."""

    category_id: int
    year: int
    month: int
    amount: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "BudgetRecord":
        """Handle from row."""
        return cls(
            category_id=row_int(row, "category_id"),
            year=row_int(row, "year"),
            month=row_int(row, "month"),
            amount=row_int(row, "amount"),
        )


@dataclass(frozen=True, slots=True)
class TransferRecord:
    """Represent TransferRecord."""

    id: str
    out_tx_id: int
    in_tx_id: int
    origin: str
    note: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TransferRecord":
        """Handle from row."""
        return cls(
            id=row_str(row, "id"),
            out_tx_id=row_int(row, "out_tx_id"),
            in_tx_id=row_int(row, "in_tx_id"),
            origin=row_str(row, "origin"),
            note=row_str(row, "note"),
            created_at=row_str(row, "created_at"),
        )


@dataclass(frozen=True, slots=True)
class TransferSplitRecord:
    """Represent TransferSplitRecord."""

    out_tx_id: int
    in_tx_id: int
    out_category_id: int | None
    in_category_id: int | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TransferSplitRecord":
        """Handle from row."""
        return cls(
            out_tx_id=row_int(row, "out_tx_id"),
            in_tx_id=row_int(row, "in_tx_id"),
            out_category_id=row_optional_int(row, "out_category_id"),
            in_category_id=row_optional_int(row, "in_category_id"),
        )
