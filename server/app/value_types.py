import datetime
from decimal import Decimal

from pydantic import JsonValue

type JsonObject = dict[str, JsonValue]
type SqliteValue = bytes | float | int | str | None
type WorkbookCellValue = (
    datetime.date | datetime.datetime | datetime.time | Decimal | float | int | str | None
)


def sqlite_int(value: SqliteValue) -> int:
    if isinstance(value, int):
        return value
    raise TypeError("SQLite value must be an integer")


def sqlite_str(value: SqliteValue) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("SQLite value must be a string")


def sqlite_optional_int(value: SqliteValue) -> int | None:
    return None if value is None else sqlite_int(value)


def sqlite_optional_str(value: SqliteValue) -> str | None:
    return None if value is None else sqlite_str(value)
