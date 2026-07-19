import pytest

from tests.conftest import login_as

pytestmark = pytest.mark.integration


def test_data_routes_require_jwt(anon):
    assert anon.get("/api/snapshot").status_code == 401
    assert anon.get("/api/groups").status_code == 401
    assert anon.post("/api/groups", json={"name": "X", "kind": "expense"}).status_code == 401
    assert anon.get("/api/snapshot", headers={"Authorization": "Bearer garbage"}).status_code == 401

    hdr = login_as(anon, "jwt@example.com")
    assert anon.get("/api/snapshot", headers=hdr).status_code == 200
    assert (
        anon.post("/api/groups", json={"name": "X", "kind": "expense"}, headers=hdr).status_code
        == 200
    )


def test_users_are_isolated(anon):
    a = login_as(anon, "alice@example.com")
    b = login_as(anon, "bob@example.com")

    r = anon.post("/api/groups", json={"name": "Bills", "kind": "expense"}, headers=a)
    assert r.status_code == 200
    gid = r.json()["id"]
    r = anon.post(
        "/api/categories", json={"name": "Rent", "groupId": gid, "keywords": ""}, headers=a
    )
    assert r.status_code == 200
    cid = r.json()["id"]
    alice_acct = anon.get("/api/accounts", headers=a).json()[0]["id"]
    r = anon.post(
        "/api/transactions",
        json={"date": "2026-01-05T00:00:00", "amount": -100, "accountId": alice_acct},
        headers=a,
    )
    assert r.status_code == 200
    tx_id = r.json()["id"]

    snap_b = anon.get("/api/snapshot", headers=b).json()
    assert snap_b["groups"] == []
    assert snap_b["categories"] == []
    assert snap_b["transactions"] == []
    assert [acc["name"] for acc in snap_b["accounts"]] == ["Cash"]

    assert (
        anon.patch(f"/api/transactions/{tx_id}", json={"amount": -1}, headers=b).status_code == 404
    )
    assert anon.delete(f"/api/transactions/{tx_id}", headers=b).status_code == 404
    assert (
        anon.patch(f"/api/categories/{cid}", json={"name": "Stolen"}, headers=b).status_code == 404
    )
    bob_acct = anon.get("/api/accounts", headers=b).json()[0]["id"]
    r = anon.post(
        "/api/transactions",
        json={"date": "2026-01-06T00:00:00", "amount": -5, "accountId": alice_acct},
        headers=b,
    )
    assert r.status_code in (400, 404)

    snap_a = anon.get("/api/snapshot", headers=a).json()
    assert len(snap_a["transactions"]) == 1
    assert snap_a["transactions"][0]["amount"] == -100
    assert bob_acct != alice_acct


def test_same_names_allowed_across_users(anon):
    a = login_as(anon, "u1@example.com")
    b = login_as(anon, "u2@example.com")
    assert (
        anon.post("/api/groups", json={"name": "Bills", "kind": "expense"}, headers=a).status_code
        == 200
    )
    assert (
        anon.post("/api/groups", json={"name": "Bills", "kind": "expense"}, headers=b).status_code
        == 200
    )
    assert anon.post("/api/accounts", json={"name": "Vault"}, headers=a).status_code == 200
    assert anon.post("/api/accounts", json={"name": "Vault"}, headers=b).status_code == 200
    assert anon.post("/api/accounts", json={"name": "Vault"}, headers=b).status_code == 409


def test_first_user_claims_legacy_data(anon):
    import app.db as dbmod

    c = dbmod.connect()
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (NULL, 'T-Bank', 'card', 'RUB', 1)"
    )
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, kind)"
        " VALUES (NULL, 'Legacy', 1, 'expense')"
    )
    c.commit()
    c.close()

    first = login_as(anon, "owner@example.com")
    snap = anon.get("/api/snapshot", headers=first).json()
    assert [a["name"] for a in snap["accounts"]] == ["T-Bank"]
    assert [g["name"] for g in snap["groups"]] == ["Legacy"]

    second = login_as(anon, "guest@example.com")
    snap2 = anon.get("/api/snapshot", headers=second).json()
    assert [a["name"] for a in snap2["accounts"]] == ["Cash"]
    assert snap2["groups"] == []
