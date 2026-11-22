# Copyright (c) 2026
"""Shared structural types for the database API used by the application."""

from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Protocol, Self, SupportsIndex, overload


class DatabaseRow(Protocol):
    """A row supporting named and positional access."""

    @overload
    def __getitem__(self, key: str) -> object: ...

    @overload
    def __getitem__(self, key: SupportsIndex) -> object: ...

    def keys(self) -> Iterable[str]:
        """Return the names of the columns in the row."""
        ...


class DatabaseCursor(Protocol):
    """The cursor operations used by application code."""

    lastrowid: int | None
    rowcount: int

    def __iter__(self) -> Iterator[DatabaseRow]:
        """Iterate over result rows."""
        ...

    def execute(
        self, sql: str, params: Sequence[object] | Mapping[str, object] = ()
    ) -> Self:
        """Execute SQL and return this cursor."""
        ...

    def fetchone(self) -> DatabaseRow | None:
        """Fetch one row, if available."""
        ...

    def fetchall(self) -> list[DatabaseRow]:
        """Fetch all remaining rows."""
        ...


class DatabaseConnection(Protocol):
    """The connection operations used by application code."""

    def cursor(self) -> DatabaseCursor:
        """Create a cursor."""
        ...

    def execute(
        self, sql: str, params: Sequence[object] | Mapping[str, object] = ()
    ) -> DatabaseCursor:
        """Execute SQL and return a cursor."""
        ...

    def executemany(
        self, sql: str, rows: Iterable[Sequence[object] | Mapping[str, object]]
    ) -> DatabaseCursor:
        """Execute SQL for each parameter set."""
        ...

    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    def rollback(self) -> None:
        """Roll back the current transaction."""
        ...

    def close(self) -> None:
        """Close the connection."""
        ...

    def __enter__(self) -> Self:
        """Enter the connection context."""
        ...

    def __exit__(
        self,
        typ: type[BaseException] | None,
        value: BaseException | None,
        tb: object,
    ) -> None:
        """Exit the connection context."""
        ...
