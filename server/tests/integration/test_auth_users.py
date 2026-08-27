import pytest
from fastapi.testclient import TestClient
from httpx2 import Response as HTTPXResponse

import monori.server.app.db as dbmod
from monori.server.app.routers.auth_router import _valid_email
from monori.server.tests.conftest import Api, login_as

pytestmark = pytest.mark.integration


def _register(
    client: TestClient,
    email: str = "user@example.com",
    password: str = "hunter2pw",
) -> HTTPXResponse:
    return client.post("/api/auth/register", json={"email": email, "password": password})


def _login(
    client: TestClient,
    email: str = "user@example.com",
    password: str = "hunter2pw",
) -> HTTPXResponse:
    return client.post("/api/auth/token", data={"username": email, "password": password})


def test_register_returns_user_without_hash(client: TestClient) -> None:
    r = _register(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "user@example.com"
    assert "id" in body
    assert "createdAt" in body
    assert "password" not in body
    assert "password_hash" not in body


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    assert _register(client).status_code == 200
    r = _register(client)
    assert r.status_code == 409


def test_register_rolls_back_when_default_account_creation_fails(client: TestClient) -> None:
    c = dbmod.connect()
    try:
        c.execute(
            "CREATE TRIGGER fail_default_account BEFORE INSERT ON accounts"
            " BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        c.commit()
    finally:
        c.close()

    with pytest.raises(Exception, match="injected"):
        _register(client, email="atomic@example.com")

    c = dbmod.connect()
    try:
        assert c.execute("SELECT 1 FROM users WHERE email='atomic@example.com'").fetchone() is None
    finally:
        c.close()


def test_register_normalizes_email(client: TestClient) -> None:
    assert _register(client, email="  Mixed@Example.COM ").status_code == 200

    assert _register(client, email="mixed@example.com").status_code == 409


@pytest.mark.parametrize(
    "alias",
    [
        "antoningrish@gmail.com",
        "a.n.t.o.n.ingrish@gmail.com",
        "anton.ingrish+shopping@gmail.com",
    ],
)
def test_register_rejects_gmail_alias_of_same_mailbox(client: TestClient, alias: str) -> None:
    assert _register(client, email="anton.ingrish@gmail.com").status_code == 200

    assert _register(client, email=alias).status_code == 409


def test_register_rejects_plus_tag_alias_on_any_domain(client: TestClient) -> None:
    assert _register(client, email="user@example.com").status_code == 200
    assert _register(client, email="user+promo@example.com").status_code == 409


def test_register_allows_dots_on_non_gmail_domain(client: TestClient) -> None:

    assert _register(client, email="a.b@example.com").status_code == 200
    assert _register(client, email="ab@example.com").status_code == 200


def test_login_works_through_a_gmail_alias(client: TestClient) -> None:
    _register(client, email="anton.ingrish@gmail.com")
    r = _login(client, email="antoningrish+phone@gmail.com")
    assert r.status_code == 200, r.text


def test_register_validates_email_and_password(client: TestClient) -> None:
    assert _register(client, email="not-an-email").status_code == 400
    assert _register(client, email="a@b.co", password="short").status_code == 400


@pytest.mark.parametrize("email", ["user@example.com", "a.b+c@sub.example.co"])
def test_valid_email_accepts(email: str) -> None:
    assert _valid_email(email)


@pytest.mark.parametrize(
    "email",
    [
        "",
        "no-at-sign",
        "@example.com",
        "user@nodot",
        "user@@example.com",
        "user@.com",
        "user@example.",
        "user name@example.com",
        "u" * 250 + "@x.com",
    ],
)
def test_valid_email_rejects(email: str) -> None:
    assert not _valid_email(email)


def test_login_returns_bearer_token(client: TestClient) -> None:
    _register(client)
    r = _login(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_and_unknown_user(client: TestClient) -> None:
    _register(client)
    wrong_password = _login(client, password="wrongpassword")
    unknown = _login(client, email="nobody@example.com")
    assert wrong_password.status_code == 401
    assert unknown.status_code == 401

    assert wrong_password.json()["detail"] == "incorrect password"
    assert unknown.json()["detail"] == "no account is registered for this email"


def test_login_is_case_insensitive_on_email(client: TestClient) -> None:
    _register(client, email="user@example.com")
    assert _login(client, email="USER@example.com").status_code == 200


def test_me_requires_and_accepts_token(anon: TestClient) -> None:
    _register(anon)
    token = _login(anon).json()["access_token"]

    assert anon.get("/api/auth/me").status_code == 401
    bad = anon.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "invalid or expired token"

    r = anon.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "user@example.com"


def test_me_rejects_token_of_deleted_user(anon: TestClient) -> None:
    client = anon
    _register(client)
    token = _login(client).json()["access_token"]

    c = dbmod.connect()
    c.execute("DELETE FROM accounts")
    c.execute("DELETE FROM category_groups")
    c.execute("DELETE FROM users")
    c.commit()
    c.close()

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["detail"] == "unknown user"


def test_default_account_is_set_cleared_and_guarded(api: Api, client: TestClient) -> None:
    """
    The default account for card-less rows is a user preference: settable to an.

    owned account, clearable back to "assign by hand", and never someone.
    else's account.
    """
    assert client.get("/api/auth/me").json()["defaultAccountId"] is None
    acct = api.default_account()

    r = client.patch("/api/auth/me", json={"defaultAccountId": acct})
    assert r.status_code == 200, r.text
    assert r.json()["defaultAccountId"] == acct
    assert client.get("/api/auth/me").json()["defaultAccountId"] == acct

    r = client.patch("/api/auth/me", json={"defaultAccountId": None})
    assert r.status_code == 200
    assert r.json()["defaultAccountId"] is None

    assert client.patch("/api/auth/me", json={"defaultAccountId": 99999}).status_code == 400

    headers = dict(client.headers)
    client.headers.update(login_as(client, "stranger@example.com"))
    assert client.patch("/api/auth/me", json={"defaultAccountId": acct}).status_code == 400
    client.headers.update(headers)


def test_deleting_the_default_account_clears_the_preference(api: Api, client: TestClient) -> None:
    first = api.default_account()
    second = api.account("Second")
    r = client.patch("/api/auth/me", json={"defaultAccountId": second})
    assert r.status_code == 200
    r = client.delete(f"/api/accounts/{second}")
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me").json()["defaultAccountId"] is None
    assert first == api.default_account()
