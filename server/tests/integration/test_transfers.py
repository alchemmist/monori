import pytest

pytestmark = pytest.mark.integration


def test_transfer_creates_linked_pair(api):
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000, comment="move")

    rows = [t for t in api.snapshot()["transactions"] if t["transferId"] == transfer_id]
    assert len(rows) == 2
    by_account = {t["accountId"]: t["amount"] for t in rows}
    assert by_account == {a: -5000, b: 5000}
    assert all(t["categoryId"] is None and t["source"] == "transfer" for t in rows)
    assert sum(t["amount"] for t in rows) == 0


def test_transfer_rejects_same_account(api, client):
    a = api.default_account()
    r = client.post(
        "/api/transfers",
        json={"fromAccountId": a, "toAccountId": a, "amount": 100, "date": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 400


def test_transfer_rejects_unknown_account(api, client):
    a = api.default_account()
    r = client.post(
        "/api/transfers",
        json={"fromAccountId": a, "toAccountId": 999, "amount": 100, "date": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 400


def test_transfer_rejects_non_positive_amount(api, client):
    a = api.default_account()
    b = api.account("Vault")
    r = client.post(
        "/api/transfers",
        json={"fromAccountId": a, "toAccountId": b, "amount": 0, "date": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 422


def test_delete_transfer_removes_both_rows(api, client):
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000)
    assert client.delete(f"/api/transfers/{transfer_id}").status_code == 200
    assert not [t for t in api.snapshot()["transactions"] if t["transferId"] == transfer_id]

    assert client.delete(f"/api/transfers/{transfer_id}").status_code == 404
