import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GroupRecord:
    id: int
    name: str
    sort: int
    kind: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "GroupRecord":
        return cls(id=row["id"], name=row["name"], sort=row["sort"], kind=row["kind"])


@dataclass(frozen=True, slots=True)
class CategoryRecord:
    id: int
    group_id: int
    name: str
    keywords: str
    sort: int
    archived: bool
    goal_target: int | None = None
    goal_status: str | None = None
    goal_target_date: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "CategoryRecord":
        keys = row.keys()
        return cls(
            id=row["id"],
            group_id=row["group_id"],
            name=row["name"],
            keywords=row["keywords"],
            sort=row["sort"],
            archived=bool(row["archived"]),
            goal_target=row["goal_target"] if "goal_target" in keys else None,
            goal_status=row["goal_status"] if "goal_status" in keys else None,
            goal_target_date=row["goal_target_date"] if "goal_target_date" in keys else None,
        )


@dataclass(frozen=True, slots=True)
class CategoryOwnershipRecord:
    id: int
    keywords: str
    goal_target: int | None
    type: str
    is_goal: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "CategoryOwnershipRecord":
        return cls(
            id=row["id"],
            keywords=row["keywords"],
            goal_target=row["goal_target"],
            type=row["type"],
            is_goal=bool(row["is_goal"]),
        )


@dataclass(frozen=True, slots=True)
class GoalGroupRecord:
    id: int
    is_goal: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "GoalGroupRecord":
        return cls(id=row["id"], is_goal=bool(row["is_goal"]))


@dataclass(frozen=True, slots=True)
class CategorySignRecord:
    id: int
    transaction_sign: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "CategorySignRecord":
        return cls(id=row["id"], transaction_sign=row["transaction_sign"])


@dataclass(frozen=True, slots=True)
class AccountRecord:
    id: int
    name: str
    type: str
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
        return cls(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            icon=row["icon"],
            color=row["color"],
            icon_image=row["icon_image"],
            currency=row["currency"],
            sort=row["sort"],
            archived=bool(row["archived"]),
            opening_balance=row["opening_balance"],
            opening_date=row["opening_date"],
            connection_id=row["connection_id"],
            bank_ref=row["bank_ref"],
            card_tails=row["card_tails"],
        )


@dataclass(frozen=True, slots=True)
class SplitRecord:
    id: int
    transaction_id: int
    category_id: int
    amount: int
    comment: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "SplitRecord":
        return cls(
            id=row["id"],
            transaction_id=row["transaction_id"],
            category_id=row["category_id"],
            amount=row["amount"],
            comment=row["comment"],
        )


@dataclass(frozen=True, slots=True)
class TransactionRecord:
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
    source: str
    hidden: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TransactionRecord":
        return cls(
            id=row["id"],
            date=row["date"],
            amount=row["amount"],
            description=row["description"],
            bank_category=row["bank_category"],
            mcc=row["mcc"],
            category_id=row["category_id"],
            account_id=row["account_id"],
            transfer_id=row["transfer_id"],
            comment=row["comment"],
            source=row["source"],
            hidden=bool(row["hidden"]),
        )


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: int
    email: str
    created_at: str
    is_admin: bool
    last_login: str | None
    default_account_id: int | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "UserRecord":
        return cls(
            id=row["id"],
            email=row["email"],
            created_at=row["created_at"],
            is_admin=bool(row["is_admin"]),
            last_login=row["last_login"],
            default_account_id=row["default_account_id"],
        )


@dataclass(frozen=True, slots=True)
class ConnectionRecord:
    id: int
    bank: str
    kind: str
    status: str
    last_sync: str | None
    last_error: str | None
    has_credentials: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ConnectionRecord":
        return cls(
            id=row["id"],
            bank=row["bank"],
            kind=row["kind"],
            status=row["status"],
            last_sync=row["last_sync"],
            last_error=row["last_error"],
            has_credentials=row["credentials_encrypted"] is not None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass(frozen=True, slots=True)
class BudgetRecord:
    category_id: int
    year: int
    month: int
    amount: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "BudgetRecord":
        return cls(
            category_id=row["category_id"],
            year=row["year"],
            month=row["month"],
            amount=row["amount"],
        )


@dataclass(frozen=True, slots=True)
class TransferRecord:
    id: str
    out_tx_id: int
    in_tx_id: int
    origin: str
    note: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TransferRecord":
        return cls(
            id=row["id"],
            out_tx_id=row["out_tx_id"],
            in_tx_id=row["in_tx_id"],
            origin=row["origin"],
            note=row["note"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True, slots=True)
class TransferSplitRecord:
    out_tx_id: int
    in_tx_id: int
    out_category_id: int | None
    in_category_id: int | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TransferSplitRecord":
        return cls(
            out_tx_id=row["out_tx_id"],
            in_tx_id=row["in_tx_id"],
            out_category_id=row["out_category_id"],
            in_category_id=row["in_category_id"],
        )
