"""Closed sets of values shared by API DTOs and database records."""

from enum import StrEnum


class AccountType(StrEnum):
    """Supported account types."""

    CARD = "card"
    CASH = "cash"
    SAVINGS = "savings"
    OTHER = "other"


class CategoryGroupKind(StrEnum):
    """Ways a category group affects the budget."""

    INCOME = "income"
    EXPENSE = "expense"
    GOAL = "goal"


class ConnectionStatus(StrEnum):
    """Lifecycle states of a bank connection."""

    DISCONNECTED = "disconnected"
    AWAITING_SMS = "awaiting_sms"
    CONNECTED = "connected"
    ERROR = "error"
    PENDING = "pending"


class TransactionSource(StrEnum):
    """Origins recorded for transactions."""

    MANUAL = "manual"
    IMPORT = "import"
    SYNC = "sync"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"
    WORKBOOK = "workbook"
    SHEETS = "sheets"


class GoalStatus(StrEnum):
    """Lifecycle states of a savings goal."""

    ACTIVE = "active"
    ACHIEVED = "achieved"
    ARCHIVED = "archived"
