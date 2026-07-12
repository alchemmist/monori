import pytest

pytestmark = pytest.mark.integration


def _group(client, name, kind):
    return client.post("/api/groups", json={"name": name, "kind": kind}).json()["id"]


def _category(client, name, group_id, keywords=""):
    return client.post(
        "/api/categories", json={"name": name, "groupId": group_id, "keywords": keywords}
    ).json()["id"]


def test_groups_crud_and_reorder(client):
    assert client.get("/api/groups").json() == []
    exp = _group(client, "Expenses", "expense")
    inc = _group(client, "Income", "income")
    assert len(client.get("/api/groups").json()) == 2

    assert (
        client.post("/api/groups", json={"name": "Expenses", "kind": "expense"}).status_code == 409
    )
    assert client.post("/api/groups", json={"name": "Bad", "kind": "nope"}).status_code == 400

    assert client.patch(f"/api/groups/{exp}", json={"name": "Fixed"}).status_code == 200
    assert client.patch(f"/api/groups/{exp}", json={"kind": "bad"}).status_code == 400
    assert client.patch("/api/groups/999", json={"name": "x"}).status_code == 404

    r = client.post("/api/groups/reorder", json={"ids": [inc, exp]})
    assert r.status_code == 200
    assert [g["id"] for g in client.get("/api/groups").json()] == [inc, exp]
    assert client.post("/api/groups/reorder", json={"ids": [inc]}).status_code == 400


def test_group_delete_guards_non_empty(client):
    exp = _group(client, "Expenses", "expense")
    _category(client, "Groceries", exp)
    assert client.delete(f"/api/groups/{exp}").status_code == 409
    assert client.delete("/api/groups/999").status_code == 404
    empty = _group(client, "Empty", "expense")
    assert client.delete(f"/api/groups/{empty}").status_code == 200


def test_categories_reorder_archive(client):
    g = _group(client, "Expenses", "expense")
    a = _category(client, "A", g)
    b = _category(client, "B", g)
    assert client.post("/api/categories/reorder", json={"ids": [b, a]}).status_code == 200
    cats = client.get("/api/snapshot").json()["categories"]
    assert [c["id"] for c in cats] == [b, a]
    assert client.post("/api/categories/reorder", json={"ids": [a]}).status_code == 400

    assert client.patch(f"/api/categories/{a}", json={"archived": True}).status_code == 200
    got = [c for c in client.get("/api/snapshot").json()["categories"] if c["id"] == a][0]
    assert got["archived"] is True
    client.patch(f"/api/categories/{a}", json={"archived": False})
    got = [c for c in client.get("/api/snapshot").json()["categories"] if c["id"] == a][0]
    assert got["archived"] is False


def test_category_merge(client):
    g = _group(client, "Expenses", "expense")
    src = _category(client, "Coffee", g, "cofix")
    dst = _category(client, "Cafe", g, "starbucks")
    client.post(
        "/api/transactions", json={"date": "2026-01-01T00:00:00", "amount": -500, "categoryId": src}
    )

    assert client.post(f"/api/categories/{src}/merge", json={"into": src}).status_code == 400
    assert client.post(f"/api/categories/{src}/merge", json={"into": 999}).status_code == 400
    assert client.post("/api/categories/999/merge", json={"into": dst}).status_code == 404

    r = client.post(f"/api/categories/{src}/merge", json={"into": dst})
    assert r.status_code == 200
    snap = client.get("/api/snapshot").json()
    assert [c["id"] for c in snap["categories"]] == [dst]
    assert snap["transactions"][0]["categoryId"] == dst
    merged = snap["categories"][0]["keywords"].split("|")
    assert set(merged) == {"starbucks", "cofix"}


def test_transaction_create_and_full_patch(client):
    g = _group(client, "Expenses", "expense")
    cat = _category(client, "Groceries", g)
    r = client.post(
        "/api/transactions",
        json={"date": "2026-02-03T10:00:00", "amount": -12345, "description": "Lenta"},
    )
    tid = r.json()["id"]
    snap = client.get("/api/snapshot").json()["transactions"][0]
    assert snap["source"] == "manual" and snap["amount"] == -12345

    assert (
        client.post(
            "/api/transactions", json={"date": "x", "amount": 1, "categoryId": 999}
        ).status_code
        == 400
    )

    client.patch(
        f"/api/transactions/{tid}",
        json={"amount": -999, "description": "Lenta market", "categoryId": cat, "comment": "hi"},
    )
    got = client.get("/api/snapshot").json()["transactions"][0]
    assert got["amount"] == -999
    assert got["description"] == "Lenta market"
    assert got["categoryId"] == cat
    assert got["comment"] == "hi"
    assert client.patch("/api/transactions/999", json={"amount": 1}).status_code == 404


def test_transaction_list_filters_and_pagination(client):
    g = _group(client, "Expenses", "expense")
    inc_g = _group(client, "Income", "income")
    food = _category(client, "Food", g)
    salary = _category(client, "Salary", inc_g)
    client.post(
        "/api/transactions",
        json={
            "date": "2026-01-05T00:00:00",
            "amount": -100,
            "description": "Lenta",
            "categoryId": food,
        },
    )
    client.post(
        "/api/transactions",
        json={
            "date": "2026-02-05T00:00:00",
            "amount": -200,
            "description": "Pyaterochka",
            "categoryId": food,
        },
    )
    client.post(
        "/api/transactions",
        json={
            "date": "2026-03-05T00:00:00",
            "amount": 500000,
            "description": "Payroll",
            "categoryId": salary,
        },
    )
    client.post(
        "/api/transactions",
        json={"date": "2026-03-06T00:00:00", "amount": -50, "description": "Cash"},
    )

    assert client.get("/api/transactions").json()["total"] == 4
    assert client.get("/api/transactions?from=2026-02-01&to=2026-02-28").json()["total"] == 1
    assert client.get(f"/api/transactions?categoryId={food}").json()["total"] == 2
    assert client.get("/api/transactions?uncategorized=true").json()["total"] == 1
    assert client.get("/api/transactions?q=payroll").json()["total"] == 1
    page = client.get("/api/transactions?limit=2&offset=0").json()
    assert len(page["rows"]) == 2 and page["total"] == 4
    assert page["rows"][0]["date"] >= page["rows"][1]["date"]


def test_transaction_bulk(client):
    g = _group(client, "Expenses", "expense")
    food = _category(client, "Food", g)
    ids = [
        client.post(
            "/api/transactions", json={"date": f"2026-01-0{i}T00:00:00", "amount": -i}
        ).json()["id"]
        for i in range(1, 4)
    ]
    r = client.post(
        "/api/transactions/bulk", json={"action": "categorize", "ids": ids, "categoryId": food}
    )
    assert r.json()["affected"] == 3
    assert client.get(f"/api/transactions?categoryId={food}").json()["total"] == 3
    assert (
        client.post("/api/transactions/bulk", json={"action": "bad", "ids": ids}).status_code == 400
    )
    assert (
        client.post("/api/transactions/bulk", json={"action": "delete", "ids": []}).json()[
            "affected"
        ]
        == 0
    )
    assert (
        client.post("/api/transactions/bulk", json={"action": "delete", "ids": ids}).json()[
            "affected"
        ]
        == 3
    )
    assert client.get("/api/transactions").json()["total"] == 0


def test_budget_bulk_and_copy(client):
    g = _group(client, "Expenses", "expense")
    a = _category(client, "A", g)
    b = _category(client, "B", g)
    client.post(
        "/api/budgets/bulk",
        json={
            "cells": [
                {"categoryId": a, "year": 2026, "month": 1, "amount": 1000},
                {"categoryId": b, "year": 2026, "month": 1, "amount": 2000},
            ]
        },
    )
    assert len(client.get("/api/snapshot").json()["budgets"]) == 2

    r = client.post(
        "/api/budgets/copy", json={"fromYear": 2026, "toYear": 2026, "fromMonth": 1, "toMonth": 2}
    )
    assert r.json()["copied"] == 2
    feb = [x for x in client.get("/api/snapshot").json()["budgets"] if x["month"] == 2]
    assert len(feb) == 2

    r = client.post("/api/budgets/copy", json={"fromYear": 2026, "toYear": 2027})
    assert r.json()["copied"] == 4
    y2027 = [x for x in client.get("/api/snapshot").json()["budgets"] if x["year"] == 2027]
    assert len(y2027) == 4

    assert (
        client.post(
            "/api/budgets/copy", json={"fromYear": 2026, "toYear": 2027, "fromMonth": 1}
        ).status_code
        == 400
    )
    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 1, "amount": 0})
    assert (
        len(
            [
                x
                for x in client.get("/api/snapshot").json()["budgets"]
                if x["year"] == 2026 and x["month"] == 1
            ]
        )
        == 1
    )


def test_import_commit_server_side_dedup(client):
    text = (
        "05.01.2026 10:00:00\t05.01.2026\t*1\tOK\t-100,00\tRUB\t-100,00\tRUB\t\tSuper\t5411\tLenta\t0\t0\t-100,00\n"
        "06.01.2026 11:00:00\t06.01.2026\t*1\tOK\t-200,00\tRUB\t-200,00\tRUB\t\tSuper\t5411\tOkey\t0\t0\t-200,00\n"
    )
    rows = client.post("/api/import/preview", json={"text": text}).json()["rows"]

    within_batch = client.post("/api/import/commit", json={"rows": [rows[0], rows[0]]}).json()
    assert within_batch["inserted"] == 1 and within_batch["skipped"] == 1
    assert client.get("/api/transactions").json()["total"] == 1

    both = client.post("/api/import/commit", json={"rows": rows}).json()
    assert both["inserted"] == 1 and both["skipped"] == 1
    assert client.get("/api/transactions").json()["total"] == 2

    resubmit = client.post("/api/import/commit", json={"rows": rows}).json()
    assert resubmit["inserted"] == 0 and resubmit["skipped"] == 2


def test_api_token_auth(client, monkeypatch):
    monkeypatch.setenv("MONORI_API_TOKEN", "s3cret")
    assert client.get("/api/snapshot").status_code == 401
    assert client.get("/api/snapshot", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.get("/api/snapshot", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
