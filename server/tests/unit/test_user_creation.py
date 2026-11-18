import sqlite3
from datetime import UTC, datetime, tzinfo
from pathlib import Path

import pytest
from fastapi import HTTPException

import monori.server.app.routers.categories as categories_router
from monori.server.app.db import connect
from monori.server.app.routers import auth_router


def test_create_user_validates_input_and_duplicate_detail(tmp_path: Path) -> None:
    connection = connect(tmp_path / "users.db")
    create_user = vars(auth_router)["create_user"]
    try:
        with pytest.raises(HTTPException) as invalid_email:
            create_user(connection, "invalid", "12345678")
        assert (invalid_email.value.status_code, invalid_email.value.detail) == (
            400,
            "invalid email",
        )

        with pytest.raises(HTTPException) as short_password:
            create_user(connection, "user@example.com", "1234567")
        assert (short_password.value.status_code, short_password.value.detail) == (
            400,
            "password must be at least 8 characters",
        )

        assert create_user(connection, "user@example.com", "12345678").email == "user@example.com"
        with pytest.raises(HTTPException) as duplicate:
            create_user(connection, "user@example.com", "12345678")
        assert (duplicate.value.status_code, duplicate.value.detail) == (
            409,
            "email already registered",
        )
    finally:
        connection.close()


def test_create_user_uses_utc_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FrozenDateTime:
        @classmethod
        def now(cls, timezone: tzinfo) -> datetime:
            assert timezone is UTC
            return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    monkeypatch.setattr(auth_router, "datetime", FrozenDateTime)
    connection = connect(tmp_path / "users.db")
    try:
        user = vars(auth_router)["create_user"](connection, "user@example.com", "12345678")
    finally:
        connection.close()

    assert user.created_at == "2026-01-02T03:04:05"


def test_first_user_adopts_unowned_rows_and_later_users_do_not(tmp_path: Path) -> None:
    connection = connect(tmp_path / "users.db")
    create_user = vars(auth_router)["create_user"]
    try:
        connection.execute("INSERT INTO accounts (name) VALUES ('Legacy Cash')")
        connection.execute(
            "INSERT INTO category_groups (name, sort, type_id) VALUES ('Legacy', 1, 2)"
        )
        connection.execute(
            "INSERT INTO bank_connections (bank, kind, created_at, updated_at)"
            " VALUES ('bank', 'kind', '2026-01-01', '2026-01-01')"
        )
        first = create_user(connection, "first@example.com", "12345678")

        assert (
            connection.execute("SELECT user_id FROM accounts WHERE name='Legacy Cash'").fetchone()[
                0
            ]
            == first.id
        )
        assert (
            connection.execute(
                "SELECT user_id FROM category_groups WHERE name='Legacy'"
            ).fetchone()[0]
            == first.id
        )
        assert (
            connection.execute("SELECT user_id FROM bank_connections WHERE bank='bank'").fetchone()[
                0
            ]
            == first.id
        )

        connection.execute("INSERT INTO accounts (name) VALUES ('Unclaimed')")
        second = create_user(connection, "second@example.com", "12345678")

        assert (
            connection.execute("SELECT user_id FROM accounts WHERE name='Unclaimed'").fetchone()[0]
            is None
        )
        accounts = connection.execute(
            "SELECT name, type, currency FROM accounts WHERE user_id=?", (second.id,)
        ).fetchall()
        assert [tuple(account) for account in accounts] == [("Cash", "cash", "RUB")]
    finally:
        connection.close()


def test_name_taken_distinguishes_duplicates_self_and_missing(tmp_path: Path) -> None:
    connection = connect(tmp_path / "categories.db")
    create_user = vars(auth_router)["create_user"]
    name_taken = vars(categories_router)["_name_taken"]
    try:
        user = create_user(connection, "user@example.com", "12345678")
        group = connection.execute(
            "INSERT INTO category_groups (user_id, name, sort, type_id) VALUES (?, 'Home', 1, 2)",
            (user.id,),
        ).lastrowid
        category = connection.execute(
            "INSERT INTO categories (group_id, name) VALUES (?, 'Food')", (group,)
        ).lastrowid
        assert isinstance(group, int)
        assert isinstance(category, int)

        assert name_taken(connection, user.id, group, "Food") is True
        assert name_taken(connection, user.id, group, "Food", category) is False
        assert name_taken(connection, user.id, group, "Missing") is False
    finally:
        connection.close()
