import pytest
from conftest import login_as

pytestmark = pytest.mark.integration

ADMIN_EMAIL = "boss@example.com"


def _make_admin(client, monkeypatch, email=ADMIN_EMAIL):
    monkeypatch.setenv("MONORI_ADMIN_EMAILS", email)
    return login_as(client, email)


def _add_tx(client, amount=-500, date="2026-07-01T12:00:00"):
    accounts = client.get("/api/snapshot").json()["accounts"]
    r = client.post(
        "/api/transactions",
        json={
            "accountId": accounts[0]["id"],
            "date": date,
            "amount": amount,
            "description": "coffee",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_admin_endpoints_reject_non_admin(client):
    for method, url in [
        ("get", "/api/admin/overview"),
        ("get", "/api/admin/users"),
        ("get", "/api/admin/users/1"),
        ("get", "/api/admin/activity"),
        ("post", "/api/admin/users"),
        ("delete", "/api/admin/users/2"),
    ]:
        r = getattr(client, method)(url)
        assert r.status_code == 403, f"{method} {url}: {r.status_code}"


def test_admin_flag_synced_from_env_at_login(anon, monkeypatch):
    monkeypatch.delenv("MONORI_ADMIN_EMAILS", raising=False)
    headers = login_as(anon, ADMIN_EMAIL)
    assert anon.get("/api/auth/me", headers=headers).json()["isAdmin"] is False

    headers = _make_admin(anon, monkeypatch)
    me = anon.get("/api/auth/me", headers=headers).json()
    assert me["isAdmin"] is True
    assert me["lastLogin"] is not None

    monkeypatch.delenv("MONORI_ADMIN_EMAILS", raising=False)
    headers = login_as(anon, ADMIN_EMAIL)
    assert anon.get("/api/auth/me", headers=headers).json()["isAdmin"] is False


def test_overview_counts_users_and_transactions(anon, monkeypatch):
    other = login_as(anon, "other@example.com")
    anon.headers.update(other)
    _add_tx(anon)
    anon.headers.clear()
    anon.headers.update(_make_admin(anon, monkeypatch))

    body = anon.get("/api/admin/overview").json()
    assert body["totals"]["users"] == 2
    assert body["totals"]["transactions"] == 1
    assert body["totals"]["accounts"] == 2
    assert body["newUsers7d"] == 2
    assert body["newUsers30d"] == 2
    assert body["activeUsers7d"] == 2
    months = {r["month"]: r["count"] for r in body["registrations"]}
    assert sum(months.values()) == 2


def test_users_list_reports_per_user_aggregates(anon, monkeypatch):
    other = login_as(anon, "other@example.com")
    anon.headers.update(other)
    _add_tx(anon, amount=-500, date="2026-07-01T12:00:00")
    _add_tx(anon, amount=-700, date="2026-07-02T12:00:00")
    anon.headers.clear()
    anon.headers.update(_make_admin(anon, monkeypatch))

    users = {u["email"]: u for u in anon.get("/api/admin/users").json()}
    assert set(users) == {"other@example.com", ADMIN_EMAIL}
    other_row = users["other@example.com"]
    assert other_row["accounts"] == 1
    assert other_row["transactions"] == 2
    assert other_row["lastTransaction"] == "2026-07-02T12:00:00"
    assert other_row["budgets"] == 0
    assert other_row["connection"] is None
    assert other_row["isAdmin"] is False
    assert users[ADMIN_EMAIL]["isAdmin"] is True


def test_user_detail_returns_accounts_transactions_and_activity(anon, monkeypatch):
    other = login_as(anon, "other@example.com")
    anon.headers.update(other)
    _add_tx(anon, amount=-500)
    uid = anon.get("/api/auth/me").json()["id"]
    anon.headers.clear()
    anon.headers.update(_make_admin(anon, monkeypatch))

    body = anon.get(f"/api/admin/users/{uid}").json()
    assert body["user"]["email"] == "other@example.com"
    assert len(body["accounts"]) == 1
    assert body["accounts"][0]["balance"] == -500
    assert body["accounts"][0]["transactions"] == 1
    assert len(body["recentTransactions"]) == 1
    assert body["recentTransactions"][0]["amount"] == -500
    assert body["recentTransactions"][0]["account"] == body["accounts"][0]["name"]
    assert len(body["recentLogins"]) == 1
    features = {r["feature"] for r in body["featureUsage"]}
    assert {"snapshot", "transactions"} <= features


def test_user_detail_404_for_unknown_user(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    assert anon.get("/api/admin/users/999").status_code == 404


def test_admin_creates_user(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    r = anon.post("/api/admin/users", json={"email": "new@example.com", "password": "hunter2pw"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "new@example.com"
    users = {u["email"] for u in anon.get("/api/admin/users").json()}
    assert "new@example.com" in users

    dup = anon.post("/api/admin/users", json={"email": "new@example.com", "password": "hunter2pw"})
    assert dup.status_code == 409
    short = anon.post("/api/admin/users", json={"email": "x@example.com", "password": "short"})
    assert short.status_code == 400


def test_admin_deletes_user_with_all_data(anon, monkeypatch):
    other = login_as(anon, "victim@example.com")
    anon.headers.update(other)
    _add_tx(anon)
    uid = anon.get("/api/auth/me").json()["id"]
    anon.headers.clear()
    anon.headers.update(_make_admin(anon, monkeypatch))

    assert anon.delete(f"/api/admin/users/{uid}").json() == {"ok": True}
    users = {u["email"] for u in anon.get("/api/admin/users").json()}
    assert "victim@example.com" not in users
    assert anon.get(f"/api/admin/users/{uid}").status_code == 404
    body = anon.get("/api/admin/overview").json()
    assert body["totals"]["transactions"] == 0
    assert anon.delete(f"/api/admin/users/{uid}").status_code == 404


def test_admin_cannot_delete_self(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    uid = anon.get("/api/auth/me").json()["id"]
    r = anon.delete(f"/api/admin/users/{uid}")
    assert r.status_code == 400


def test_activity_reports_feature_usage_and_logins(anon, monkeypatch):
    other = login_as(anon, "other@example.com")
    anon.get("/api/snapshot", headers=other)
    anon.get("/api/snapshot", headers=other)
    anon.headers.update(_make_admin(anon, monkeypatch))

    body = anon.get("/api/admin/activity").json()
    features = {r["feature"]: r["count"] for r in body["features"]}
    assert features["snapshot"] >= 2
    assert "auth" not in features
    assert len(body["daily"]) >= 1
    assert body["daily"][0]["count"] == sum(features.values())
    emails = [r["email"] for r in body["recentLogins"]]
    assert emails[0] == ADMIN_EMAIL
    assert "other@example.com" in emails


def test_usage_middleware_ignores_anonymous_and_garbage_tokens(anon, monkeypatch):
    anon.get("/api/snapshot")
    anon.get("/api/snapshot", headers={"Authorization": "Bearer garbage"})
    anon.headers.update(_make_admin(anon, monkeypatch))

    body = anon.get("/api/admin/activity").json()
    features = {r["feature"]: r["count"] for r in body["features"]}
    assert features.get("snapshot", 0) == 0
