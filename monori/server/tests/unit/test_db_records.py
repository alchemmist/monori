"""Tests for checked SQLite row adapters."""

import pathlib
import sqlite3
import sys
from collections.abc import Callable
from typing import cast

import pytest

from monori.server.app.db_records import (
    RowTypeError,
    RowValueError,
    row_bool,
    row_enum,
    row_int,
    row_optional_int,
    row_optional_str,
    row_str,
)
from monori.server.app.domain_types import AccountType


def _row() -> sqlite3.Row:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT 1 AS integer_value, 'card' AS text_value, NULL AS null_value, 2 AS invalid_bool,"
        " 'crypto' AS invalid_enum"
    ).fetchone()
    assert row is not None
    return cast("sqlite3.Row", row)


def test_row_adapters_read_valid_values() -> None:
    row = _row()

    assert row_int(row, "integer_value") == 1
    assert row_str(row, "text_value") == "card"
    assert row_optional_int(row, "null_value") is None
    assert row_optional_str(row, "null_value") is None
    assert row_bool(row, "integer_value") is True
    assert row_enum(row, "text_value", AccountType) is AccountType.CARD


@pytest.mark.parametrize(
    ("reader", "key", "error"),
    [
        (row_int, "text_value", RowTypeError),
        (row_str, "integer_value", RowTypeError),
        (row_optional_int, "text_value", RowTypeError),
        (row_optional_str, "integer_value", RowTypeError),
        (row_bool, "invalid_bool", RowValueError),
        (row_int, "missing_value", RowValueError),
    ],
)
def test_row_adapters_reject_wrong_sql_shapes(
    reader: Callable[[sqlite3.Row, str], int | str | None | bool],
    key: str,
    error: type[Exception],
) -> None:
    row = _row()

    with pytest.raises(error):
        reader(row, key)


def test_row_enum_rejects_unknown_persisted_value() -> None:
    row = _row()

    with pytest.raises(RowValueError):
        row_enum(row, "invalid_enum", AccountType)
