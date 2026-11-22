# Copyright (c) 2026
import re
from datetime import UTC, datetime, tzinfo
from pathlib import Path

import pytest
from fastapi import HTTPException

from monori.server.app.db import connect
from monori.server.app.routers import auth_router

STAMPED_AT = "2026-01-02T03:04:05"


class FrozenDateTime:
    @classmethod
    def now(cls, timezone: tzinfo) -> datetime:
        assert timezone is UTC
        return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    "raw_email",
    [
        "",
        "a b@example.com",
        "a@b@c.example.com",
        "@example.com",
        "no-at-sign.example.com",
        "a@example..com",
    ],
)
def test_create_user_rejects_misshaped_emails(raw_email: str, tmp_path: Path) -> None:
    connection = connect(tmp_path / "users.db")
    create_user = vars(auth_router)["create_user"]
    try:
        with pytest.raises(HTTPException) as err:
            create_user(connection, raw_email, "12345678")
        assert (err.value.status_code, err.value.detail) == (400, "invalid email")
    finally:
        connection.close()


def test_create_user_accepts_email_at_the_length_limit(tmp_path: Path) -> None:
    local = "a" * (254 - len("@example.com"))
    connection = connect(tmp_path / "users.db")
    create_user = vars(auth_router)["create_user"]
    try:
        user = create_user(connection, f"{local}@example.com", "12345678")
        assert user.email == f"{local}@example.com"
    finally:
        connection.close()


def test_create_user_is_disabled_in_sso_only_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MONORI_SSO_ONLY_USER_IDS", "1")
    connection = connect(tmp_path / "users.db")
    create_user = vars(auth_router)["create_user"]
    try:
        with pytest.raises(HTTPException) as err:
            create_user(connection, "user@example.com", "12345678")
        assert (err.value.status_code, err.value.detail) == (403, "Account creation is disabled")
    finally:
        connection.close()


def test_record_login_grants_admin_and_stamps_the_moment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MONORI_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setattr(auth_router, "datetime", FrozenDateTime)
    connection = connect(tmp_path / "users.db")
    record_login = vars(auth_router)["record_login"]
    create_user = vars(auth_router)["create_user"]
    try:
        user = create_user(connection, "admin@example.com", "12345678")
        record_login(connection, user.id, "admin@example.com")

        assert (
            connection.execute("SELECT is_admin FROM users WHERE id=?", (user.id,)).fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT last_login FROM users WHERE id=?", (user.id,)).fetchone()[0]
            == STAMPED_AT
        )
        events = connection.execute(
            "SELECT kind, created_at FROM activity_events WHERE user_id=?", (user.id,)
        ).fetchall()
        assert [tuple(event) for event in events] == [("login", STAMPED_AT)]
    finally:
        connection.close()


def test_record_login_strips_admin_from_everyone_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MONORI_ADMIN_EMAILS", raising=False)
    monkeypatch.setattr(auth_router, "datetime", FrozenDateTime)
    connection = connect(tmp_path / "users.db")
    record_login = vars(auth_router)["record_login"]
    create_user = vars(auth_router)["create_user"]
    try:
        user = create_user(connection, "user@example.com", "12345678")
        connection.execute("UPDATE users SET is_admin=1 WHERE id=?", (user.id,))
        record_login(connection, user.id, "user@example.com")
        connection.commit()

        assert (
            connection.execute("SELECT is_admin FROM users WHERE id=?", (user.id,)).fetchone()[0]
            == 0
        )
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
            connection.execute("SELECT last_login FROM users WHERE id=?", (user.id,)).fetchone()[0],
        )
    finally:
        connection.close()
