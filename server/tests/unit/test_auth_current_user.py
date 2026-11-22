# Copyright (c) 2026
"""Check that the current_user dependency resolves, maps and rejects precisely."""

from pathlib import Path

import pytest
from fastapi import HTTPException

import monori.server.app.db as dbmod
from monori.server.app.auth import AuthenticatedUser, current_user
from monori.server.app.security import create_access_token

EMAIL = "a@example.com"
CREATED_AT = "2026-01-01T00:00:00"
LAST_LOGIN = "2026-02-02T10:00:00"
DEFAULT_ACCOUNT_ID = 7


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dbmod.DatabaseConnection:
    monkeypatch.delenv("MONORI_SSO_ONLY_USER_IDS", raising=False)
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "auth.db"))
    connection = dbmod.connect()
    connection.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at, is_admin,"
        " last_login)"
        " VALUES (?, ?, 'x', ?, 1, ?)",
        (EMAIL, EMAIL, CREATED_AT, LAST_LOGIN),
    )
    connection.execute(
        "INSERT INTO accounts (id, user_id, name, sort, opening_balance)"
        " VALUES (7, 1, 'Cash', 1, 0)"
    )
    connection.execute(
        "UPDATE users SET default_account_id=? WHERE email=?", (DEFAULT_ACCOUNT_ID, EMAIL)
    )
    connection.commit()
    yield connection
    connection.close()


@pytest.mark.usefixtures("db")
def test_current_user_resolves_the_signed_in_user() -> None:
    user = current_user(create_access_token(1))
    assert isinstance(user, AuthenticatedUser)
    assert user.id == 1
    assert user.email == EMAIL
    assert user.created_at == CREATED_AT
    assert user.is_admin is True
    assert user.last_login == LAST_LOGIN
    assert user.default_account_id == DEFAULT_ACCOUNT_ID


@pytest.mark.usefixtures("db")
def test_current_user_rejects_malformed_token() -> None:
    with pytest.raises(HTTPException) as err:
        current_user("not-a-token")
    assert (err.value.status_code, err.value.detail) == (401, "invalid or expired token")


@pytest.mark.usefixtures("db")
def test_current_user_rejects_token_for_missing_user() -> None:
    with pytest.raises(HTTPException) as err:
        current_user(create_access_token(999))
    assert (err.value.status_code, err.value.detail) == (401, "unknown user")


@pytest.mark.usefixtures("db")
def test_to_api_dict_copies_every_user_field() -> None:
    response = current_user(create_access_token(1)).to_api_dict()
    assert response.id == 1
    assert response.email == EMAIL
    assert response.created_at == CREATED_AT
    assert response.is_admin is True
    assert response.last_login == LAST_LOGIN
    assert response.default_account_id == DEFAULT_ACCOUNT_ID
