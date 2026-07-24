import pytest

from app.admin import admin_emails, admin_user, feature_from_path, user_id_from_auth_header
from app.security import create_access_token


def test_admin_emails_parses_and_normalizes(monkeypatch):
    monkeypatch.setenv("MONORI_ADMIN_EMAILS", " Boss@Example.com , , second@e.co ")
    assert admin_emails() == {"boss@example.com", "second@e.co"}


def test_admin_emails_empty_when_unset(monkeypatch):
    monkeypatch.delenv("MONORI_ADMIN_EMAILS", raising=False)
    assert admin_emails() == set()


def test_admin_user_rejects_non_admin():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        admin_user({"id": 1, "isAdmin": False})
    assert e.value.status_code == 403


def test_admin_user_passes_admin_through():
    user = {"id": 1, "isAdmin": True}
    assert admin_user(user) is user


@pytest.mark.parametrize(
    ("path", "feature"),
    [
        ("/api/transactions", "transactions"),
        ("/api/transactions/5", "transactions"),
        ("/api/snapshot", "snapshot"),
        ("/api/import/workbook/preview", "import"),
        ("/api/auth/token", None),
        ("/api/", None),
        ("/api", None),
        ("/assets/app.js", None),
        ("/", None),
        ("api/transactions", None),
    ],
)
def test_feature_from_path(path, feature):
    assert feature_from_path(path) == feature


def test_user_id_from_auth_header_roundtrip(monkeypatch):
    monkeypatch.setenv("MONORI_AUTH_SECRET", "unit-test-secret")
    token = create_access_token(42)
    assert user_id_from_auth_header(f"Bearer {token}") == 42
    assert user_id_from_auth_header(f"bearer {token}") == 42


@pytest.mark.parametrize(
    "header",
    [None, "", "Basic abc", "Bearer not-a-jwt"],
)
def test_user_id_from_auth_header_rejects_bad_headers(monkeypatch, header):
    monkeypatch.setenv("MONORI_AUTH_SECRET", "unit-test-secret")
    assert user_id_from_auth_header(header) is None
