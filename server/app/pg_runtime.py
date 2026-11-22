# Copyright (c) 2026
"""PostgreSQL-backed implementation of the application's small DB-API subset."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar, Self, SupportsIndex, cast, overload, override

import psycopg
from psycopg import ClientCursor
from psycopg import Connection as PsycopgConnection
from psycopg import Cursor as PsycopgCursor

if TYPE_CHECKING:
    from types import TracebackType

    from psycopg.rows import RowMaker

IDENTITIES = {
    "accounts",
    "activity_events",
    "bank_connections",
    "categories",
    "category_groups",
    "category_group_types",
    "import_batches",
    "splits",
    "transactions",
    "users",
}


class Record(tuple[object, ...]):
    """Represent a database row as a tuple with named-column lookup."""

    __slots__ = ()

    _fields: ClassVar[tuple[str, ...]] = ()

    def keys(self) -> tuple[str, ...]:
        """Return the column names in this record."""
        return type(self)._fields

    @overload
    def __getitem__(self, key: str) -> object: ...

    @overload
    def __getitem__(self, key: SupportsIndex) -> object: ...

    @overload
    def __getitem__(
        self, key: slice[SupportsIndex | None, SupportsIndex | None, SupportsIndex | None]
    ) -> tuple[object, ...]: ...

    @override
    def __getitem__(
        self,
        key: str
        | SupportsIndex
        | slice[SupportsIndex | None, SupportsIndex | None, SupportsIndex | None],
    ) -> object | tuple[object, ...]:
        """Return a value by position or column name."""
        if isinstance(key, str):
            try:
                key = type(self)._fields.index(key)
            except ValueError as exc:
                raise IndexError(key) from exc
        return super().__getitem__(key)


def record_factory(cur: PsycopgCursor[object]) -> RowMaker[Record]:
    """Create named tuple rows using the cursor's column names."""
    names = tuple(d.name for d in cur.description or ())
    record_type = cast(
        "type[Record]", type("Record", (Record,), {"__slots__": (), "_fields": names})
    )

    def build(values: Sequence[object]) -> Record:
        normalized = (
            int(value)
            if isinstance(value, Decimal) and value == value.to_integral_value()
            else value
            for value in values
        )
        return record_type(normalized)

    return build


class Cursor:
    """Adapt a psycopg cursor to the application's DB-API subset."""

    def __init__(self, conn: Connection) -> None:
        """Initialize the cursor adapter."""
        self.conn = conn
        self.inner: PsycopgCursor[Record] = conn.raw.cursor()
        self.lastrowid: int | None = None

    def __iter__(self) -> Iterator[Record]:
        """Iterate over result rows."""
        return iter(self.inner)

    def __getattr__(self, key: str) -> object:
        """Delegate cursor attributes to psycopg."""
        return getattr(self.inner, key)

    def execute(self, sql: str, params: Sequence[object] | Mapping[str, object] = ()) -> Self:
        """Execute SQL after adapting SQLite syntax."""
        statement = sql.strip()
        lowered = statement.lower()
        statement = _translate_pragma(statement, lowered)
        if lowered.startswith(("insert ", "update ", "delete ")) or lowered == "begin immediate":
            self.conn.lock()
        if lowered == "begin immediate":
            return self
        statement = _translate_json_each(statement)
        if lowered.startswith("insert or ignore into "):
            statement = (
                re.sub("^insert or ignore into ", "INSERT INTO ", statement, flags=re.IGNORECASE)
                + " ON CONFLICT DO NOTHING"
            )
        match = re.match(r"INSERT\s+INTO\s+(\w+)", statement, re.IGNORECASE)
        identity = bool(
            match and match[1].lower() in IDENTITIES and "RETURNING" not in statement.upper()
        )
        if identity:
            statement += " RETURNING id"
        if params:
            statement = statement.replace("%", "%%")
            statement = (
                re.sub(r"(?<!:):(\w+)", r"%(\1)s", statement)
                if isinstance(params, Mapping)
                else statement.replace("?", "%s")
            )
        try:
            self.inner.execute(statement, params or None)
        except psycopg.IntegrityError as exc:
            message = "database integrity constraint"
            raise sqlite3.IntegrityError(message) from exc
        if identity and self.inner.rowcount:
            row = cast("Record", self.inner.fetchone())
            self.lastrowid = cast("int", row[0])
        else:
            self.lastrowid = None
        return self


class Connection:
    """Adapt a psycopg connection to the application's DB-API subset."""

    def __init__(self, url: str) -> None:
        """Open a PostgreSQL connection."""
        self.raw: PsycopgConnection[Record] = psycopg.connect(
            url, cursor_factory=ClientCursor, row_factory=record_factory, connect_timeout=5
        )
        self.locked = False

    def lock(self) -> None:
        """Acquire the transaction-level application write lock."""
        if not self.locked:
            self.raw.execute("SELECT pg_advisory_xact_lock(1297043023)").close()
            self.locked = True

    def cursor(self) -> Cursor:
        """Create an adapted cursor."""
        return Cursor(self)

    def execute(self, sql: str, params: Sequence[object] | Mapping[str, object] = ()) -> Cursor:
        """Execute a statement and return its cursor."""
        return self.cursor().execute(sql, params)

    def executemany(
        self, sql: str, rows: Iterable[Sequence[object] | Mapping[str, object]]
    ) -> Cursor:
        """Execute a statement for each parameter set."""
        cur = self.cursor()
        for params in rows:
            cur.execute(sql, params)
        return cur

    def commit(self) -> None:
        """Commit the transaction and clear the lock state."""
        self.raw.commit()
        self.locked = False

    def rollback(self) -> None:
        """Roll back the transaction and clear the lock state."""
        self.raw.rollback()
        self.locked = False

    def close(self) -> None:
        """Close the PostgreSQL connection."""
        self.raw.close()

    def __enter__(self) -> Self:
        """Return this connection as a context manager."""
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Commit on success and roll back on exceptions."""
        if typ is None:
            self.commit()
        else:
            self.rollback()


def _translate_pragma(statement: str, lowered: str) -> str:
    if lowered == "pragma foreign_keys=on":
        return "SELECT 1"
    if lowered == "pragma page_count":
        return "SELECT pg_database_size(current_database())"
    if lowered == "pragma page_size":
        return "SELECT 1"
    return statement


def _translate_json_each(statement: str) -> str:
    if "SELECT value FROM json_each(?)" not in statement:
        return statement
    if "t.source IN" in statement:
        return statement.replace(
            "SELECT value FROM json_each(?)",
            "SELECT value::text FROM json_array_elements_text(?::json) AS elem(value)",
        )
    return statement.replace(
        "SELECT value FROM json_each(?)",
        "SELECT value::bigint FROM json_array_elements_text(?::json) AS elem(value)",
    )
