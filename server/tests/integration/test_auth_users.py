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


@pytest.mark.parametrize(
    "alias",
    [
        "antoningrish@gmail.com",
        "a.n.t.o.n.ingrish@gmail.com",
        "anton.ingrish+shopping@gmail.com",
    ],
)
def test_register_rejects_gmail_alias_of_same_mailbox(client, alias):
    assert _register(client, email="anton.ingrish@gmail.com").status_code == 200
    # a Gmail alias (dots / +tag) resolves to the same inbox and is rejected
    assert _register(client, email=alias).status_code == 409


def test_register_rejects_plus_tag_alias_on_any_domain(client):
    assert _register(client, email="user@example.com").status_code == 200
    assert _register(client, email="user+promo@example.com").status_code == 409


def test_register_allows_dots_on_non_gmail_domain(client):
    # dots only collapse for Gmail; other providers keep them distinct
    assert _register(client, email="a.b@example.com").status_code == 200
    assert _register(client, email="ab@example.com").status_code == 200


def test_login_works_through_a_gmail_alias(client):
    _register(client, email="anton.ingrish@gmail.com")
    r = _login(client, email="antoningrish+phone@gmail.com")
    assert r.status_code == 200, r.text


def test_register_validates_email_and_password(client):
    assert _register(client, email="not-an-email").status_code == 400
    assert _register(client, email="a@b.co", password="short").status_code == 400


@pytest.mark.parametrize("email", ["user@example.com", "a.b+c@sub.example.co"])
def test_valid_email_accepts(email):
    from app.routers.auth_router import _valid_email

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
def test_valid_email_rejects(email):
    from app.routers.auth_router import _valid_email

    assert not _valid_email(email)


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


def test_me_requires_and_accepts_token(anon):
    _register(anon)
    token = _login(anon).json()["access_token"]

    assert anon.get("/api/auth/me").status_code == 401
    bad = anon.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "invalid or expired token"

    r = anon.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "user@example.com"


def test_me_rejects_token_of_deleted_user(anon):
    client = anon
    _register(client)
    token = _login(client).json()["access_token"]

    import app.db as dbmod

    c = dbmod.connect()
    c.execute("DELETE FROM accounts")
    c.execute("DELETE FROM category_groups")
    c.execute("DELETE FROM users")
    c.commit()
    c.close()

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["detail"] == "unknown user"
