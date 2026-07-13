import pytest

pytestmark = pytest.mark.integration


def test_snapshot_serialization_contract(api, client):
    """Pin the exact shape every serializer emits — API consumers depend on it."""
    g = api.group("Expenses", "expense")
    cat = api.category("Food", g, "lenta|okey")
    client.patch(f"/api/categories/{cat}", json={"archived": True})
    tx = api.tx(
        "2026-01-05T10:00:00",
        -12345,
        description="Lenta",
        bankCategory="Super",
        mcc="5411",
        categoryId=cat,
        comment="note",
    )
    client.put("/api/budgets", json={"categoryId": cat, "year": 2026, "month": 3, "amount": 5000})
    snap = api.snapshot()
    assert snap["groups"] == [{"id": g, "name": "Expenses", "sort": 1, "kind": "expense"}]
    assert snap["categories"] == [
        {
            "id": cat,
            "groupId": g,
            "name": "Food",
            "keywords": "lenta|okey",
            "sort": 1,
            "archived": True,
        }
    ]
    assert snap["transactions"] == [
        {
            "id": tx,
            "date": "2026-01-05T10:00:00",
            "amount": -12345,
            "description": "Lenta",
            "bankCategory": "Super",
            "mcc": "5411",
            "categoryId": cat,
            "comment": "note",
            "source": "manual",
        }
    ]
    assert snap["budgets"] == [{"categoryId": cat, "year": 2026, "month": 3, "amount": 5000}]


def test_snapshot_ordering_is_deterministic(api):
    """Rows sharing a sort key fall back to id, so the order is stable."""
    a = api.tx("2026-01-01T00:00:00", -1)
    b = api.tx("2026-01-01T00:00:00", -2)  # same timestamp as a
    c = api.tx("2026-01-01T00:00:00", -3)
    ids = [t["id"] for t in api.snapshot()["transactions"]]
    assert ids == [a, b, c]
