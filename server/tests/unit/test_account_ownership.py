# Copyright (c) 2026
"""Check that account and connection lookups reject what the caller does not own."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import HTTPException

from monori.server.app.db import DatabaseConnection, connect
from monori.server.app.routers.accounts import _owned_connection, _require_account


@pytest.fixture
def db(tmp_path: Path) -> Iterator[DatabaseConnection]:
    connection = connect(tmp_path / "ownership.db")
    connection.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('a@example.com', 'a@example.com', 'x', '2026-01-01T00:00:00')"
    )
    connection.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('b@example.com', 'b@example.com', 'x', '2026-01-01T00:00:00')"
    )
    # user 1 owns account 10 and connection 100; user 2 owns account 20.
    connection.execute("INSERT INTO accounts (user_id, name, sort) VALUES (1, 'A cash', 1)")
    connection.execute("INSERT INTO accounts (user_id, name, sort) VALUES (2, 'B cash', 1)")
    connection.execute("UPDATE accounts SET id=10 WHERE user_id=1 AND name='A cash'")
    connection.execute("UPDATE accounts SET id=20 WHERE user_id=2 AND name='B cash'")
    connection.execute(
        "INSERT INTO bank_connections (id, user_id, bank, kind, created_at, updated_at)"
        " VALUES (100, 1, 'tbank', 'tbank', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
    )
    yield connection
    connection.close()


def test_require_account_accepts_owner(db: DatabaseConnection) -> None:
    _require_account(db, 10, 1)


def test_require_account_rejects_foreign_account_with_404(db: DatabaseConnection) -> None:
    with pytest.raises(HTTPException) as err:
        _require_account(db, 20, 1)
    assert (err.value.status_code, err.value.detail) == (404, "account not found")


def test_require_account_rejects_missing_account_with_404(db: DatabaseConnection) -> None:
    with pytest.raises(HTTPException) as err:
        _require_account(db, 9999, 1)
    assert (err.value.status_code, err.value.detail) == (404, "account not found")


def test_owned_connection_accepts_owner(db: DatabaseConnection) -> None:
    _owned_connection(db, 100, 1)


def test_owned_connection_rejects_foreign_connection_with_400(db: DatabaseConnection) -> None:
    with pytest.raises(HTTPException) as err:
        _owned_connection(db, 100, 2)
    assert (err.value.status_code, err.value.detail) == (400, "unknown connection")


def test_owned_connection_rejects_missing_connection_with_400(db: DatabaseConnection) -> None:
    with pytest.raises(HTTPException) as err:
        _owned_connection(db, 9999, 1)
    assert (err.value.status_code, err.value.detail) == (400, "unknown connection")
