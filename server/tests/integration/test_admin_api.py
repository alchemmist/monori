import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.deps import IdResponse, SnapshotResponse
from tests.conftest import login_as

pytestmark = pytest.mark.integration

ADMIN_EMAIL = "boss@example.com"


def _make_admin(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    email: str = ADMIN_EMAIL,
) -> dict[str, str]:
    monkeypatch.setenv("MONORI_ADMIN_EMAILS", email)
    return login_as(client, email)


def _add_tx(client: TestClient, amount: int = -500, date: str = "2026-07-01T12:00:00") -> int:
    snapshot = TypeAdapter(SnapshotResponse).validate_python(client.get("/api/snapshot").json())
    r = client.post(
        "/api/transactions",
        json={
            "accountId": snapshot.accounts[0].id,
            "date": date,
            "amount": amount,
            "description": "coffee",
        },
    )
    assert r.status_code == 200, r.text
    response = TypeAdapter(IdResponse).validate_python(r.json())
    assert response.id is not None
    return response.id


def test_admin_endpoints_reject_non_admin(client: TestClient) -> None:
    for method, url in [
        ("get", "/api/admin/overview"),
        ("get", "/api/admin/users"),
        ("get", "/api/admin/users/1"),
        ("get", "/api/admin/users/1/transactions"),
        ("get", "/api/admin/activity"),
        ("post", "/api/admin/users"),
        ("delete", "/api/admin/users/2"),
    ]:
        r = getattr(client, method)(url)
        assert r.status_code == 403, f"{method} {url}: {r.status_code}"


def test_admin_flag_synced_from_env_at_login(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_admin_flag_matches_env_through_a_gmail_alias(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.setenv("MONORI_ADMIN_EMAILS", "admin.person@gmail.com")
    headers = login_as(anon, "adminperson+work@gmail.com")
    assert anon.get("/api/auth/me", headers=headers).json()["isAdmin"] is True


def test_overview_counts_users_and_transactions(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    assert body["dbSizeBytes"] > 0


def test_users_list_reports_per_user_aggregates(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_user_detail_returns_accounts_transactions_and_activity(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = login_as(anon, "other@example.com")
    anon.headers.update(other)
    _add_tx(anon, amount=-500)
    uid = anon.get("/api/auth/me").json()["id"]
    anon.headers.clear()
    anon.headers.update(_make_admin(anon, monkeypatch))

    body = anon.get(f"/api/admin/users/{uid}").json()
    assert body["user"]["email"] == "other@example.com"
    assert len(body["accounts"]) == 1

    assert body["accounts"][0]["balance"] == 0
    assert body["accounts"][0]["transactions"] == 1
    assert len(body["recentTransactions"]) == 1
    assert body["recentTransactions"][0]["amount"] == -500
    assert body["recentTransactions"][0]["account"] == body["accounts"][0]["name"]
    assert len(body["recentLogins"]) == 1
    features = {r["feature"] for r in body["featureUsage"]}
    assert {"snapshot", "transactions"} <= features


def test_user_detail_404_for_unknown_user(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anon.headers.update(_make_admin(anon, monkeypatch))
    assert anon.get("/api/admin/users/999").status_code == 404


def test_user_transactions_returns_every_row_newest_first(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = login_as(anon, "other@example.com")
    anon.headers.update(other)
    _add_tx(anon, amount=-500, date="2026-07-01T12:00:00")
    _add_tx(anon, amount=-700, date="2026-07-03T12:00:00")
    _add_tx(anon, amount=-300, date="2026-07-02T12:00:00")
    uid = anon.get("/api/auth/me").json()["id"]
    anon.headers.clear()
    anon.headers.update(_make_admin(anon, monkeypatch))

    rows = anon.get(f"/api/admin/users/{uid}/transactions").json()
    assert [r["date"] for r in rows] == [
        "2026-07-03T12:00:00",
        "2026-07-02T12:00:00",
        "2026-07-01T12:00:00",
    ]
    assert {
        "id",
        "amount",
        "description",
        "account",
        "category",
        "mcc",
        "comment",
        "source",
    } <= set(rows[0])


def test_user_transactions_paginates_with_limit_and_offset(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = login_as(anon, "paged@example.com")
    anon.headers.update(other)
    for day in range(1, 6):
        _add_tx(anon, amount=-100 * day, date=f"2026-07-0{day}T12:00:00")
    uid = anon.get("/api/auth/me").json()["id"]
    anon.headers.clear()
    anon.headers.update(_make_admin(anon, monkeypatch))

    base = f"/api/admin/users/{uid}/transactions"
    page1 = anon.get(f"{base}?limit=2&offset=0").json()
    page2 = anon.get(f"{base}?limit=2&offset=2").json()
    assert [r["date"] for r in page1] == ["2026-07-05T12:00:00", "2026-07-04T12:00:00"]
    assert [r["date"] for r in page2] == ["2026-07-03T12:00:00", "2026-07-02T12:00:00"]

    assert anon.get(f"{base}?limit=99999").status_code == 422
    assert anon.get(f"{base}?offset=-1").status_code == 422


def test_user_transactions_404_for_unknown_user(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anon.headers.update(_make_admin(anon, monkeypatch))
    assert anon.get("/api/admin/users/999/transactions").status_code == 404


def test_admin_creates_user(anon: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_admin_deletes_user_with_all_data(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_admin_cannot_delete_self(anon: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    anon.headers.update(_make_admin(anon, monkeypatch))
    uid = anon.get("/api/auth/me").json()["id"]
    r = anon.delete(f"/api/admin/users/{uid}")
    assert r.status_code == 400


def test_activity_reports_feature_usage_and_logins(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_bulk_delete_removes_only_selected_transactions(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = login_as(anon, "bulk@example.com")
    anon.headers.update(other)
    kept = _add_tx(anon, amount=-100, date="2026-07-01T12:00:00")
    doomed = [_add_tx(anon, amount=-100 * d, date=f"2026-07-0{d}T13:00:00") for d in range(2, 6)]
    uid = anon.get("/api/auth/me").json()["id"]
    anon.headers.clear()
    anon.headers.update(_make_admin(anon, monkeypatch))

    r = anon.post(f"/api/admin/users/{uid}/transactions/delete", json={"ids": doomed})
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": 4}
    rows = anon.get(f"/api/admin/users/{uid}/transactions").json()
    assert [t["id"] for t in rows] == [kept]


def test_bulk_delete_is_all_or_nothing_across_users(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim = login_as(anon, "victim2@example.com")
    anon.headers.update(victim)
    foreign = _add_tx(anon)
    anon.headers.clear()
    owner = login_as(anon, "owner@example.com")
    anon.headers.update(owner)
    own = _add_tx(anon)
    uid = anon.get("/api/auth/me").json()["id"]
    anon.headers.clear()
    anon.headers.update(_make_admin(anon, monkeypatch))

    r = anon.post(f"/api/admin/users/{uid}/transactions/delete", json={"ids": [own, foreign]})
    assert r.status_code == 400
    assert anon.get(f"/api/admin/users/{uid}/transactions").json()[0]["id"] == own

    empty = anon.post(f"/api/admin/users/{uid}/transactions/delete", json={"ids": []})
    assert empty.status_code == 400
    unknown = anon.post("/api/admin/users/999/transactions/delete", json={"ids": [own]})
    assert unknown.status_code == 404


def test_bulk_delete_rejects_non_admin(anon: TestClient) -> None:
    headers = login_as(anon, "pleb@example.com")
    r = anon.post("/api/admin/users/1/transactions/delete", json={"ids": [1]}, headers=headers)
    assert r.status_code == 403


def test_usage_middleware_ignores_anonymous_and_garbage_tokens(
    anon: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anon.get("/api/snapshot")
    anon.get("/api/snapshot", headers={"Authorization": "Bearer garbage"})
    anon.headers.update(_make_admin(anon, monkeypatch))

    body = anon.get("/api/admin/activity").json()
    features = {r["feature"]: r["count"] for r in body["features"]}
    assert features.get("snapshot", 0) == 0
