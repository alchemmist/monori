# Copyright (c) 2026
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from monori.server.app.deps import SnapshotResponse
from monori.server.tests.conftest import AccountOptions, Api, TransactionOptions

pytestmark = pytest.mark.integration


def test_snapshot_serialization_contract(api: Api, client: TestClient) -> None:
    """Pin the exact shape every serializer emits — API consumers depend on it."""
    g = api.group("Expenses", "expense")
    cat = api.category("Food", g, "lenta|okey")
    client.patch(f"/api/categories/{cat}", json={"archived": True})
    tx = api.tx(
        "2026-01-05T10:00:00",
        -12345,
        TransactionOptions(
            description="Lenta",
            bank_category="Super",
            mcc="5411",
            category_id=cat,
            comment="note",
        ),
    )
    client.put("/api/budgets", json={"categoryId": cat, "year": 2026, "month": 3, "amount": 5000})
    snap = api.snapshot()
    serialized = TypeAdapter(SnapshotResponse).dump_python(snap, mode="json")
    assert serialized["accounts"] == [
        {
            "id": 1,
            "name": "Cash",
            "type": "cash",
            "icon": "wallet",
            "color": "#5b6472",
            "icon_image": None,
            "currency": "RUB",
            "sort": 1,
            "archived": False,
            "opening_balance": 0,
            "opening_base_amount": 0,
            "opening_date": None,
            "connection_id": None,
            "bank_ref": "",
            "card_tails": [],
        },
    ]
    assert serialized["groups"] == [{"id": g, "name": "Expenses", "sort": 1, "kind": "expense"}]
    assert serialized["categories"] == [
        {
            "id": cat,
            "group_id": g,
            "name": "Food",
            "keywords": "lenta|okey",
            "sort": 1,
            "archived": True,
            "goal_target": None,
            "goal_status": None,
            "goal_target_date": None,
        },
    ]
    assert serialized["transactions"] == [
        {
            "id": tx,
            "date": "2026-01-05T10:00:00",
            "amount": -12345,
            "currency": "RUB",
            "base_amount": -12345,
            "account_amount": -12345,
            "description": "Lenta",
            "bank_category": "Super",
            "mcc": "5411",
            "category_id": cat,
            "account_id": 1,
            "transfer_id": None,
            "comment": "note",
            "source": "manual",
            "hidden": False,
            "splits": [],
        },
    ]
    assert serialized["budgets"] == [{"category_id": cat, "year": 2026, "month": 3, "amount": 5000}]


def test_snapshot_ordering_is_deterministic(api: Api) -> None:
    """Rows sharing a sort key fall back to id, so the order is stable."""
    a = api.tx("2026-01-01T00:00:00", -1)
    b = api.tx("2026-01-01T00:00:00", -2)
    c = api.tx("2026-01-01T00:00:00", -3)
    ids = [transaction.id for transaction in api.snapshot().transactions]
    assert ids == [a, b, c]


def test_serialized_account_amounts_use_historical_rates(api: Api, client: TestClient) -> None:
    with sqlite3.connect(os.environ["MONORI_DB"]) as connection:
        connection.executemany(
            "INSERT INTO exchange_rates (day, code, rub_per_unit, source)"
            " VALUES (?, 'USD', ?, 'manual')",
            [("2026-01-01", 80), ("2026-07-01", 90)],
        )
    foreign = api.account("USD savings", AccountOptions(currency="USD", opening_balance=100))
    response = client.patch(f"/api/accounts/{foreign}", json={"openingDate": "2026-01-01"})
    assert response.status_code == 200, response.text
    transaction = api.tx(
        "2026-01-05T12:00:00",
        -100,
        TransactionOptions(currency="USD"),
    )
    snapshot = api.snapshot()
    assert (
        next(account for account in snapshot.accounts if account.id == foreign).opening_base_amount
        == 8000
    )
    row = next(row for row in snapshot.transactions if row.id == transaction)
    assert (row.currency, row.amount, row.base_amount, row.account_amount) == (
        "USD",
        -100,
        -8000,
        -8000,
    )
    response = client.get("/api/transactions")
    assert response.status_code == 200, response.text
    assert response.json()["rows"][0]["accountAmount"] == -8000
    assert response.json()["rows"][0]["baseAmount"] == -8000
