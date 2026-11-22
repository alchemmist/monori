# Copyright (c) 2026
"""Database value and record contracts shared by SQLite and PostgreSQL callers."""

import re
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict
from typing import cast

import pytest

from monori.server.app.db_records import (
    AccountRecord,
    BudgetRecord,
    CategoryOwnershipRecord,
    CategoryRecord,
    CategorySignRecord,
    ConnectionRecord,
    GoalGroupRecord,
    GroupRecord,
    RowTypeError,
    RowValueError,
    SplitRecord,
    TransactionRecord,
    TransferRecord,
    TransferSplitRecord,
    UserRecord,
    db_int,
    db_optional_int,
    db_optional_str,
    db_str,
    row_bool,
    row_enum,
    row_int,
    row_optional_int,
    row_optional_str,
    row_str,
)
from monori.server.app.db_types import DatabaseRow
from monori.server.app.domain_types import (
    AccountType,
    CategoryGroupKind,
    ConnectionStatus,
    GoalStatus,
    TransactionSource,
)
from monori.server.app.pg_runtime import Record

type Cell = int | float | str | bytes | None
type RecordValue = (
    AccountRecord
    | BudgetRecord
    | CategoryOwnershipRecord
    | CategoryRecord
    | CategorySignRecord
    | ConnectionRecord
    | GoalGroupRecord
    | GroupRecord
    | SplitRecord
    | TransactionRecord
    | TransferRecord
    | TransferSplitRecord
    | UserRecord
)


def _sql_row(values: dict[str, Cell]) -> sqlite3.Row:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        # Column names are fixed test data, not external SQL input.
        query = "SELECT " + ", ".join(f'? AS "{key}"' for key in values)
        row = connection.execute(query, tuple(values.values())).fetchone()
        assert isinstance(row, sqlite3.Row)
        return row


def _pg_row(values: dict[str, Cell]) -> Record:
    row_type = cast(
        "type[Record]", type("TestRecord", (Record,), {"__slots__": (), "_fields": tuple(values)})
    )
    return row_type(values.values())


@pytest.fixture(params=["sqlite", "postgres"])
def make_row(request: pytest.FixtureRequest) -> Callable[[dict[str, Cell]], DatabaseRow]:
    return _sql_row if request.param == "sqlite" else _pg_row


@pytest.mark.parametrize("reader", [db_int, db_optional_int])
@pytest.mark.parametrize("value", [True, False, 1.0, "1", b"1"])
def test_integer_values_reject_coercion(
    reader: Callable[[Cell, str], int | None],
    value: Cell,
) -> None:
    message = f"SQL column 'amount' must be an int, got {type(value).__name__}"
    with pytest.raises(RowTypeError, match=f"^{re.escape(message)}$"):
        reader(value, "amount")


@pytest.mark.parametrize("reader", [db_str, db_optional_str])
@pytest.mark.parametrize("value", [1, False, b"text", 1.0])
def test_text_values_reject_coercion(
    reader: Callable[[Cell, str], str | None],
    value: Cell,
) -> None:
    message = f"SQL column 'description' must be a str, got {type(value).__name__}"
    with pytest.raises(RowTypeError, match=f"^{re.escape(message)}$"):
        reader(value, "description")


@pytest.mark.parametrize(
    ("reader", "expected"),
    [(db_int, "an int"), (db_str, "a str")],
)
def test_required_values_reject_null_with_default_context(
    reader: Callable[[None], int | str],
    expected: str,
) -> None:
    with pytest.raises(
        RowTypeError, match=f"^SQL column 'value' must be {expected}, got NoneType$"
    ):
        reader(None)


@pytest.mark.parametrize("value", [0, -17, 42])
def test_nullable_integers_preserve_non_null_values(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
    value: int,
) -> None:
    assert db_int(value) == value
    assert db_optional_int(value) == value
    assert row_optional_int(make_row({"amount": value}), "amount") == value


@pytest.mark.parametrize("value", ["", "card", "кириллица"])
def test_nullable_text_preserves_non_null_values(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
    value: str,
) -> None:
    assert db_str(value) == value
    assert db_optional_str(value) == value
    assert row_optional_str(make_row({"description": value}), "description") == value


def test_nullable_values_accept_only_explicit_null(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
) -> None:
    assert db_optional_int(None) is None
    assert db_optional_str(None) is None
    row = make_row({"value": None})
    assert row_optional_int(row, "value") is None
    assert row_optional_str(row, "value") is None


@pytest.mark.parametrize("reader", [row_int, row_str, row_optional_int, row_optional_str, row_bool])
def test_missing_columns_report_the_key_and_chain_the_lookup_error(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
    reader: Callable[[DatabaseRow, str], int | str | None],
) -> None:
    with pytest.raises(
        RowValueError, match=r"^SQL row is missing required column 'absent'$"
    ) as error:
        reader(make_row({"other": 1}), "absent")
    assert isinstance(error.value.__cause__, IndexError)


@pytest.mark.parametrize(("value", "expected"), [(0, False), (1, True)])
def test_boolean_values_are_actual_booleans(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
    value: int,
    *,
    expected: bool,
) -> None:
    assert row_bool(make_row({"archived": value}), "archived") is expected


@pytest.mark.parametrize("value", [-1, 2, 10])
def test_boolean_values_reject_other_integers(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
    value: int,
) -> None:
    with pytest.raises(RowValueError, match=f"^SQL column 'archived' must be 0 or 1, got {value}$"):
        row_bool(make_row({"archived": value}), "archived")


@pytest.mark.parametrize("value", [None, "1", 1.0])
def test_boolean_values_require_integer_storage(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
    value: Cell,
) -> None:
    with pytest.raises(RowTypeError, match=r"^SQL column 'archived' must be an int, got "):
        row_bool(make_row({"archived": value}), "archived")


def test_enum_error_preserves_column_enum_name_and_cause(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
) -> None:
    with pytest.raises(
        RowValueError, match=r"^SQL column 'kind' contains an invalid AccountType$"
    ) as error:
        row_enum(make_row({"kind": "crypto"}), "kind", AccountType)
    assert isinstance(error.value.__cause__, ValueError)
    assert not isinstance(error.value.__cause__, RowValueError)


def test_enum_requires_text_without_wrapping_type_errors(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
) -> None:
    with pytest.raises(RowTypeError, match=r"^SQL column 'kind' must be a str, got int$"):
        row_enum(make_row({"kind": 1}), "kind", AccountType)
    assert row_enum(make_row({"kind": "cash"}), "kind", AccountType) is AccountType.CASH


@pytest.mark.parametrize(
    "expected",
    [
        GroupRecord(11, "Income", 23, CategoryGroupKind.INCOME),
        CategoryRecord(
            id=12,
            group_id=34,
            name="Holiday",
            keywords="travel|hotel",
            sort=56,
            archived=True,
            goal_target=789,
            goal_status=GoalStatus.ACTIVE,
            goal_target_date="2027-03-04",
        ),
        CategoryOwnershipRecord(13, "rent|home", 246, CategoryGroupKind.GOAL, is_goal=False),
        GoalGroupRecord(14, is_goal=True),
        CategorySignRecord(15, -1),
        AccountRecord(
            id=16,
            name="Savings",
            type=AccountType.SAVINGS,
            icon="wallet",
            color="#abcdef",
            icon_image="image-data",
            currency="EUR",
            sort=27,
            archived=False,
            opening_balance=-12345,
            opening_date="2025-01-02",
            connection_id=38,
            bank_ref="bank-ref",
            card_tails="1234,5678",
        ),
        SplitRecord(17, 28, 39, -456, "split note"),
        TransactionRecord(
            id=18,
            date="2026-02-03",
            amount=-678,
            description="groceries",
            bank_category="food",
            mcc="5411",
            category_id=29,
            account_id=40,
            transfer_id="transfer-id",
            comment="transaction note",
            source=TransactionSource.IMPORT,
            hidden=True,
        ),
        UserRecord(
            id=19,
            email="user@example.com",
            created_at="2026-01-02",
            is_admin=False,
            last_login="2026-04-05",
            default_account_id=30,
        ),
        ConnectionRecord(
            id=20,
            bank="bank",
            kind="api",
            status=ConnectionStatus.CONNECTED,
            last_sync="2026-05-06",
            last_error="last error",
            has_credentials=True,
            created_at="2026-01-01",
            updated_at="2026-06-07",
        ),
        BudgetRecord(21, 2026, 8, 43210),
        TransferRecord("transfer-22", 33, 44, "manual", "transfer note", "2026-07-08"),
        TransferSplitRecord(23, 45, 67, 89),
    ],
    ids=lambda record: type(record).__name__,
)
def test_record_adapters_preserve_every_selected_field(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
    expected: RecordValue,
) -> None:
    values = {
        key: int(value) if isinstance(value, bool) else value
        for key, value in asdict(expected).items()
    }
    if isinstance(expected, ConnectionRecord):
        del values["has_credentials"]
        values["credentials_encrypted"] = b"encrypted"
    actual = type(expected).from_row(make_row(values))
    assert actual == expected


@pytest.mark.parametrize(
    ("goals", "target", "status", "date"),
    [
        ({}, None, None, None),
        ({"goal_target": None, "goal_status": None, "goal_target_date": None}, None, None, None),
        ({"goal_target": 0}, 0, None, None),
        ({"goal_status": "achieved"}, None, GoalStatus.ACHIEVED, None),
        ({"goal_target_date": ""}, None, None, ""),
    ],
    ids=["not-selected", "null", "zero-target", "status-only", "empty-date"],
)
def test_category_goal_columns_are_independently_optional(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
    goals: dict[str, Cell],
    target: int | None,
    status: GoalStatus | None,
    date: str | None,
) -> None:
    values: dict[str, Cell] = {
        "id": 1,
        "group_id": 2,
        "name": "Goal",
        "keywords": "",
        "sort": 3,
        "archived": 0,
    }
    actual = CategoryRecord.from_row(make_row(values | goals))
    assert actual == CategoryRecord(
        id=1,
        group_id=2,
        name="Goal",
        keywords="",
        sort=3,
        archived=False,
        goal_target=target,
        goal_status=status,
        goal_target_date=date,
    )


@pytest.mark.parametrize(
    ("column", "value", "error"),
    [
        ("goal_target", "100", RowTypeError),
        ("goal_status", 1, RowTypeError),
        ("goal_status", "unknown", RowValueError),
        ("goal_target_date", 20260101, RowTypeError),
    ],
)
def test_selected_goal_columns_are_validated(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
    column: str,
    value: Cell,
    error: type[Exception],
) -> None:
    values: dict[str, Cell] = {
        "id": 1,
        "group_id": 2,
        "name": "Goal",
        "keywords": "",
        "sort": 3,
        "archived": 0,
        column: value,
    }
    with pytest.raises(error, match=column):
        CategoryRecord.from_row(make_row(values))


@pytest.mark.parametrize(
    ("credentials", "expected"), [(None, False), (b"", True), (b"secret", True)]
)
def test_credentials_presence_is_not_truthiness(
    make_row: Callable[[dict[str, Cell]], DatabaseRow],
    credentials: Cell,
    *,
    expected: bool,
) -> None:
    row = make_row(
        {
            "id": 1,
            "bank": "bank",
            "kind": "api",
            "status": "disconnected",
            "last_sync": None,
            "last_error": None,
            "credentials_encrypted": credentials,
            "created_at": "2026-01-01",
            "updated_at": "2026-02-02",
        }
    )
    actual = ConnectionRecord.from_row(row)
    assert actual.has_credentials is expected
    assert actual.last_sync is None
    assert actual.last_error is None
