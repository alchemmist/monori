import pytest

pytestmark = pytest.mark.integration


def test_budget_put_upsert_and_delete(api, client):
    g = api.group("Expenses")
    a = api.category("A", g)
    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 1, "amount": 1000})
    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 1, "amount": 1500})
    budgets = api.snapshot()["budgets"]
    assert len(budgets) == 1 and budgets[0]["amount"] == 1500
    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 1, "amount": 0})
    assert api.snapshot()["budgets"] == []
    r = client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 13, "amount": 5})
    assert r.status_code == 422


def test_budget_bulk_and_copy_overwrites(api, client):
    g = api.group("Expenses")
    a = api.category("A", g)
    b = api.category("B", g)
    client.post(
        "/api/budgets/bulk",
        json={
            "cells": [
                {"categoryId": a, "year": 2026, "month": 1, "amount": 1000},
                {"categoryId": b, "year": 2026, "month": 1, "amount": 2000},
                {"categoryId": a, "year": 2026, "month": 1, "amount": 0},
            ]
        },
    )
    jan = [x for x in api.snapshot()["budgets"] if x["month"] == 1]
    assert {x["categoryId"] for x in jan} == {b}

    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 2, "amount": 777})
    copy = client.post(
        "/api/budgets/copy",
        json={"fromYear": 2026, "toYear": 2026, "fromMonth": 1, "toMonth": 2},
    )
    assert copy.json()["copied"] == 1
    feb = [x for x in api.snapshot()["budgets"] if x["month"] == 2]
    assert len(feb) == 1 and feb[0]["categoryId"] == b and feb[0]["amount"] == 2000

    year_copy = client.post("/api/budgets/copy", json={"fromYear": 2026, "toYear": 2027})
    assert year_copy.json()["copied"] == 2
    assert len([x for x in api.snapshot()["budgets"] if x["year"] == 2027]) == 2


def test_budget_copy_validation_and_empty_source(api, client):
    assert (
        client.post(
            "/api/budgets/copy", json={"fromYear": 2026, "toYear": 2027, "fromMonth": 1}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/budgets/copy", json={"fromYear": 2026, "toYear": 2027, "toMonth": 1}
        ).status_code
        == 400
    )

    g = api.group("Expenses")
    a = api.category("A", g)
    client.put("/api/budgets", json={"categoryId": a, "year": 2027, "month": 1, "amount": 500})
    empty = client.post(
        "/api/budgets/copy", json={"fromYear": 2026, "toYear": 2027, "fromMonth": 1, "toMonth": 1}
    )
    assert empty.json()["copied"] == 0
    assert api.snapshot()["budgets"] == []


def test_budget_rejects_unknown_category(client):
    r = client.put(
        "/api/budgets", json={"categoryId": 999, "year": 2026, "month": 1, "amount": 100}
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown category"
