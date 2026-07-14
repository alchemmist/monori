import pytest

pytestmark = pytest.mark.integration


def test_default_account_exists(api):
    accounts = api.snapshot()["accounts"]
    assert [a["name"] for a in accounts] == ["T-Bank"]
    assert accounts[0]["type"] == "card" and accounts[0]["currency"] == "RUB"


def test_account_crud_and_uniqueness(api, client):
    cash = api.account("Cash", type="cash", openingBalance=5000)
    row = api.acct(cash)
    assert row["type"] == "cash" and row["openingBalance"] == 5000

    dup = client.post("/api/accounts", json={"name": "Cash"})
    assert dup.status_code == 409

    bad_type = client.post("/api/accounts", json={"name": "Weird", "type": "crypto"})
    assert bad_type.status_code == 400

    client.patch(f"/api/accounts/{cash}", json={"name": "Wallet", "archived": True})
    row = api.acct(cash)
    assert row["name"] == "Wallet" and row["archived"] is True


def test_reorder_accounts(api, client):
    a = api.account("A")
    b = api.account("B")
    default = api.default_account()
    r = client.post("/api/accounts/reorder", json={"ids": [b, a, default]})
    assert r.status_code == 200
    order = [x["id"] for x in api.snapshot()["accounts"]]
    assert order == [b, a, default]

    bad = client.post("/api/accounts/reorder", json={"ids": [b, a]})
    assert bad.status_code == 400


def test_delete_reassigns_transactions(api, client):
    default = api.default_account()
    cash = api.account("Cash")
    tx = api.tx("2026-03-01T10:00:00", -1000, accountId=cash)

    no_target = client.delete(f"/api/accounts/{cash}")
    assert no_target.status_code == 400

    ok = client.delete(f"/api/accounts/{cash}?reassignTo={default}")
    assert ok.status_code == 200
    assert api.tx_by(tx)["accountId"] == default
    assert cash not in [a["id"] for a in api.snapshot()["accounts"]]


def test_cannot_delete_last_account(api, client):
    default = api.default_account()
    r = client.delete(f"/api/accounts/{default}")
    assert r.status_code == 400


def test_empty_account_deletes_without_target(api, client):
    acc = api.account("Scratch")
    r = client.delete(f"/api/accounts/{acc}")
    assert r.status_code == 200


def test_transactions_filter_by_account(api, client):
    default = api.default_account()
    cash = api.account("Cash")
    api.tx("2026-03-01T10:00:00", -1000, accountId=default)
    api.tx("2026-03-02T10:00:00", -2000, accountId=cash)
    only_cash = client.get(f"/api/transactions?accountId={cash}").json()
    assert only_cash["total"] == 1 and only_cash["rows"][0]["accountId"] == cash


def test_import_targets_account(api, client):
    cash = api.account("Cash")
    rows = api.preview(api.statement)
    client.post("/api/import/commit", json={"accountId": cash, "rows": rows})
    imported = client.get(f"/api/transactions?accountId={cash}").json()
    assert imported["total"] == 2

    bad = client.post("/api/import/commit", json={"accountId": 999, "rows": rows})
    assert bad.status_code == 400
