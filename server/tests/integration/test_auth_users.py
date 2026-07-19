import pytest

pytestmark = pytest.mark.integration


def _register(client, email="user@example.com", password="hunter2pw"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def _login(client, email="user@example.com", password="hunter2pw"):
    return client.post("/api/auth/token", data={"username": email, "password": password})


def test_register_returns_user_without_hash(client):
    r = _register(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "user@example.com"
    assert "id" in body and "createdAt" in body
    assert "password" not in body and "password_hash" not in body


def test_register_rejects_duplicate_email(client):
    assert _register(client).status_code == 200
    r = _register(client)
    assert r.status_code == 409


def test_register_normalizes_email(client):
    assert _register(client, email="  Mixed@Example.COM ").status_code == 200
    # a differently-cased duplicate is rejected
    assert _register(client, email="mixed@example.com").status_code == 409


def test_register_validates_email_and_password(client):
    assert _register(client, email="not-an-email").status_code == 400
    assert _register(client, email="a@b.co", password="short").status_code == 400


def test_login_returns_bearer_token(client):
    _register(client)
    r = _login(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_and_unknown_user(client):
    _register(client)
    assert _login(client, password="wrongpassword").status_code == 401
    assert _login(client, email="nobody@example.com").status_code == 401


def test_login_is_case_insensitive_on_email(client):
    _register(client, email="user@example.com")
    assert _login(client, email="USER@example.com").status_code == 200


def test_me_requires_and_accepts_token(client):
    _register(client)
    token = _login(client).json()["access_token"]

    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    )

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "user@example.com"
