import pytest

pytestmark = pytest.mark.integration

STMT = (
    "05.01.2026 10:00:00\t05.01.2026\t*1\tOK\t-100,00\tRUB\t-100,00\tRUB\t\tSuper\t5411\tLenta\t0\t0\t-100,00\n"  # noqa: E501
    "06.01.2026 11:00:00\t06.01.2026\t*1\tOK\t-200,00\tRUB\t-200,00\tRUB\t\tSuper\t5411\tOkey\t0\t0\t-200,00\n"  # noqa: E501
)


def _group(client, name, kind):
    r = client.post("/api/groups", json={"name": name, "kind": kind})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _category(client, name, group_id, keywords=""):
    r = client.post(
        "/api/categories", json={"name": name, "groupId": group_id, "keywords": keywords}
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _tx(client, date, amount, **kw):
    r = client.post("/api/transactions", json={"date": date, "amount": amount, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _snap(client):
    return client.get("/api/snapshot").json()


def _cat(client, cat_id):
    return next(c for c in _snap(client)["categories"] if c["id"] == cat_id)


def _tx_by_id(client, tx_id):
    return next(t for t in _snap(client)["transactions"] if t["id"] == tx_id)


# ---------------------------------------------------------------- serialization


def test_snapshot_serialization_contract(client):
    """Pin the exact shape every serializer emits — API consumers depend on it."""
    g = _group(client, "Expenses", "expense")
    cat = _category(client, "Food", g, "lenta|okey")
    client.patch(f"/api/categories/{cat}", json={"archived": True})
    tx = _tx(
        client,
        "2026-01-05T10:00:00",
        -12345,
        description="Lenta",
        bankCategory="Super",
        mcc="5411",
        categoryId=cat,
        comment="note",
    )
    client.put("/api/budgets", json={"categoryId": cat, "year": 2026, "month": 3, "amount": 5000})
    snap = _snap(client)
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


# --------------------------------------------------------------------------- groups


def test_groups_full_lifecycle(client):
    assert client.get("/api/groups").json() == []
    exp = _group(client, "Expenses", "expense")
    _group(client, "Income", "income")
    groups = client.get("/api/groups").json()
    assert [g["name"] for g in groups] == ["Expenses", "Income"]
    assert [g["sort"] for g in groups] == [1, 2]
    assert groups[0]["kind"] == "expense"

    # patch name and kind together
    assert (
        client.patch(f"/api/groups/{exp}", json={"name": "Fixed", "kind": "income"}).status_code
        == 200
    )
    g = next(x for x in client.get("/api/groups").json() if x["id"] == exp)
    assert g["name"] == "Fixed" and g["kind"] == "income"


def test_group_validation_and_conflicts(client):
    exp = _group(client, "Expenses", "expense")
    assert (
        client.post("/api/groups", json={"name": "Expenses", "kind": "expense"}).status_code == 409
    )
    assert client.post("/api/groups", json={"name": "Bad", "kind": "nope"}).status_code == 400
    assert client.post("/api/groups", json={"name": "", "kind": "expense"}).status_code == 422
    _group(client, "Income", "income")
    assert client.patch(f"/api/groups/{exp}", json={"name": "Income"}).status_code == 409
    assert client.patch(f"/api/groups/{exp}", json={"kind": "bad"}).status_code == 400
    assert client.patch("/api/groups/999", json={"name": "x"}).status_code == 404


def test_group_reorder_persists_and_validates(client):
    a = _group(client, "A", "expense")
    b = _group(client, "B", "expense")
    c = _group(client, "C", "expense")
    assert client.post("/api/groups/reorder", json={"ids": [c, a, b]}).status_code == 200
    assert [g["id"] for g in client.get("/api/groups").json()] == [c, a, b]
    assert [g["sort"] for g in client.get("/api/groups").json()] == [1, 2, 3]
    assert client.post("/api/groups/reorder", json={"ids": [a, b]}).status_code == 400  # missing
    assert (
        client.post("/api/groups/reorder", json={"ids": [a, b, c, 999]}).status_code == 400
    )  # extra
    assert client.post("/api/groups/reorder", json={"ids": [a, a, b]}).status_code == 400  # dup


def test_group_delete_guards_non_empty(client):
    exp = _group(client, "Expenses", "expense")
    _category(client, "Groceries", exp)
    assert client.delete(f"/api/groups/{exp}").status_code == 409
    assert client.delete("/api/groups/999").status_code == 404
    empty = _group(client, "Empty", "expense")
    assert client.delete(f"/api/groups/{empty}").status_code == 200
    assert empty not in [g["id"] for g in client.get("/api/groups").json()]


# ----------------------------------------------------------------------- categories


def test_category_create_sort_and_conflicts(client):
    g = _group(client, "Expenses", "expense")
    a = _category(client, "A", g)
    b = _category(client, "B", g)
    cats = _snap(client)["categories"]
    assert [c["sort"] for c in cats] == [1, 2]
    assert client.post("/api/categories", json={"name": "A", "groupId": g}).status_code == 409
    assert client.post("/api/categories", json={"name": "X", "groupId": 999}).status_code == 400
    assert client.post("/api/categories", json={"name": "", "groupId": g}).status_code == 422
    assert a != b


def test_category_patch_move_group_and_name(client):
    g1 = _group(client, "Expenses", "expense")
    g2 = _group(client, "Income", "income")
    a = _category(client, "A", g1)
    _category(client, "B", g1)
    assert client.patch(f"/api/categories/{a}", json={"groupId": g2}).status_code == 200
    assert _cat(client, a)["groupId"] == g2
    assert client.patch(f"/api/categories/{a}", json={"groupId": 999}).status_code == 400
    assert client.patch(f"/api/categories/{a}", json={"name": "B"}).status_code == 409
    assert client.patch("/api/categories/999", json={"name": "z"}).status_code == 404
    assert client.patch(f"/api/categories/{a}", json={"keywords": "x|y"}).status_code == 200
    assert _cat(client, a)["keywords"] == "x|y"


def test_category_reorder_and_archive_roundtrip(client):
    g = _group(client, "Expenses", "expense")
    a = _category(client, "A", g)
    b = _category(client, "B", g)
    assert client.post("/api/categories/reorder", json={"ids": [b, a]}).status_code == 200
    assert [c["id"] for c in _snap(client)["categories"]] == [b, a]
    assert client.post("/api/categories/reorder", json={"ids": [a]}).status_code == 400

    assert client.patch(f"/api/categories/{a}", json={"archived": True}).status_code == 200
    assert _cat(client, a)["archived"] is True
    client.patch(f"/api/categories/{a}", json={"archived": False})
    assert _cat(client, a)["archived"] is False


def test_category_delete_reassign_never_shifts(client):
    g = _group(client, "Expenses", "expense")
    a = _category(client, "A", g)
    b = _category(client, "B", g)
    tx = _tx(client, "2026-01-01T00:00:00", -500, categoryId=a)
    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 1, "amount": 1000})
    client.put("/api/budgets", json={"categoryId": b, "year": 2026, "month": 1, "amount": 2000})

    assert client.delete(f"/api/categories/{a}?reassignTo=999").status_code == 400
    assert client.delete(f"/api/categories/{a}?reassignTo={b}").status_code == 200
    snap = _snap(client)
    # transaction moved to b, a's budget gone, b's budget untouched
    assert _tx_by_id(client, tx)["categoryId"] == b
    budgets = {x["categoryId"]: x["amount"] for x in snap["budgets"]}
    assert budgets == {b: 2000}


def test_category_delete_without_reassign_uncategorizes(client):
    g = _group(client, "Expenses", "expense")
    a = _category(client, "A", g)
    tx = _tx(client, "2026-01-01T00:00:00", -500, categoryId=a)
    assert client.delete(f"/api/categories/{a}").status_code == 200
    assert _tx_by_id(client, tx)["categoryId"] is None
    assert client.delete("/api/categories/999").status_code == 404


def test_category_merge_moves_tx_and_unions_keywords(client):
    g = _group(client, "Expenses", "expense")
    src = _category(client, "Coffee", g, "cofix|STARBUCKS")
    dst = _category(client, "Cafe", g, "starbucks|shokoladnitsa")
    tx = _tx(client, "2026-01-01T00:00:00", -500, categoryId=src)
    client.put("/api/budgets", json={"categoryId": src, "year": 2026, "month": 1, "amount": 900})

    assert client.post(f"/api/categories/{src}/merge", json={"into": src}).status_code == 400
    assert client.post(f"/api/categories/{src}/merge", json={"into": 999}).status_code == 400
    assert client.post("/api/categories/999/merge", json={"into": dst}).status_code == 404

    assert client.post(f"/api/categories/{src}/merge", json={"into": dst}).status_code == 200
    snap = _snap(client)
    assert [c["id"] for c in snap["categories"]] == [dst]
    assert _tx_by_id(client, tx)["categoryId"] == dst
    # case-insensitive union, target order first, source extras appended
    assert _cat(client, dst)["keywords"].split("|") == ["starbucks", "shokoladnitsa", "cofix"]
    # source budget removed with the source category
    assert snap["budgets"] == []


def test_merge_with_empty_keywords(client):
    g = _group(client, "Expenses", "expense")
    src = _category(client, "Src", g, "")
    dst = _category(client, "Dst", g, "coffee")
    client.post(f"/api/categories/{src}/merge", json={"into": dst})
    assert _cat(client, dst)["keywords"] == "coffee"

    src2 = _category(client, "Src2", g, "tea")
    dst2 = _category(client, "Dst2", g, "")
    client.post(f"/api/categories/{src2}/merge", json={"into": dst2})
    assert _cat(client, dst2)["keywords"] == "tea"


# --------------------------------------------------------------------- transactions


def test_transaction_create_variants(client):
    g = _group(client, "Expenses", "expense")
    cat = _category(client, "Food", g)
    manual = _tx(client, "2026-02-03T10:00:00", -12345, description="Lenta", categoryId=cat)
    row = _tx_by_id(client, manual)
    assert row["source"] == "manual" and row["amount"] == -12345 and row["categoryId"] == cat

    uncat = _tx(client, "2026-02-04T10:00:00", -1, categoryId=0)
    assert _tx_by_id(client, uncat)["categoryId"] is None

    bad = client.post("/api/transactions", json={"date": "x", "amount": 1, "categoryId": 999})
    assert bad.status_code == 400 and "category" in bad.json()["detail"].lower()


def test_transaction_partial_patch_preserves_other_fields(client):
    g = _group(client, "Expenses", "expense")
    cat = _category(client, "Food", g)
    tx = _tx(client, "2026-02-03T10:00:00", -100, description="Lenta", categoryId=cat, comment="a")
    client.patch(f"/api/transactions/{tx}", json={"comment": "b"})
    row = _tx_by_id(client, tx)
    assert row["comment"] == "b"
    assert row["amount"] == -100 and row["description"] == "Lenta" and row["categoryId"] == cat

    # full edit + uncategorize
    client.patch(
        f"/api/transactions/{tx}",
        json={"amount": -999, "date": "2026-05-05T00:00:00", "description": "X", "categoryId": 0},
    )
    row = _tx_by_id(client, tx)
    assert (
        row["amount"] == -999 and row["date"] == "2026-05-05T00:00:00" and row["categoryId"] is None
    )
    assert client.patch(f"/api/transactions/{tx}", json={"categoryId": 999}).status_code == 400
    assert client.patch("/api/transactions/999", json={"amount": 1}).status_code == 404


def test_transaction_patch_recomputes_hash_for_dedup(client):
    """Editing date/amount/description must recompute the dedup hash: a statement
    row that matched the old content should stop being a duplicate."""
    # manual tx mirrors the first statement row exactly (05.01.2026, -100,00, Lenta)
    tx = _tx(client, "2026-01-05T10:00:00", -10000, description="Lenta")
    prev = client.post("/api/import/preview", json={"text": STMT}).json()["rows"]
    assert prev[0]["duplicate"] is True

    # change the description -> hash changes -> the same statement row is fresh again
    client.patch(f"/api/transactions/{tx}", json={"description": "Something else"})
    prev = client.post("/api/import/preview", json={"text": STMT}).json()["rows"]
    assert prev[0]["duplicate"] is False


def test_transaction_list_filters_combined_and_pagination(client):
    g = _group(client, "Expenses", "expense")
    inc = _group(client, "Income", "income")
    food = _category(client, "Food", g)
    salary = _category(client, "Salary", inc)
    _tx(client, "2026-01-05T00:00:00", -100, description="Lenta", categoryId=food)
    _tx(client, "2026-02-05T00:00:00", -200, description="Pyaterochka", categoryId=food)
    _tx(client, "2026-03-05T00:00:00", 500000, description="Payroll", categoryId=salary)
    _tx(client, "2026-03-06T00:00:00", -50, description="Cash")

    assert client.get("/api/transactions").json()["total"] == 4
    assert client.get("/api/transactions?from=2026-02-01&to=2026-02-28").json()["total"] == 1
    assert client.get(f"/api/transactions?categoryId={food}").json()["total"] == 2
    assert client.get("/api/transactions?uncategorized=true").json()["total"] == 1
    assert client.get("/api/transactions?q=PAYROLL").json()["total"] == 1  # case-insensitive
    # combined: food AND date range
    assert client.get(f"/api/transactions?categoryId={food}&from=2026-02-01").json()["total"] == 1
    # uncategorized overrides categoryId
    assert (
        client.get(f"/api/transactions?uncategorized=true&categoryId={food}").json()["total"] == 1
    )

    page = client.get("/api/transactions?limit=2&offset=0").json()
    assert len(page["rows"]) == 2 and page["total"] == 4
    assert page["rows"][0]["date"] >= page["rows"][1]["date"]  # newest first
    assert (
        client.get("/api/transactions?limit=2&offset=2").json()["rows"][0]["date"]
        < page["rows"][1]["date"]
    )
    assert client.get("/api/transactions?limit=0").status_code == 422
    assert client.get("/api/transactions?limit=99999").status_code == 422


def test_transaction_bulk_actions(client):
    g = _group(client, "Expenses", "expense")
    food = _category(client, "Food", g)
    ids = [_tx(client, f"2026-01-0{i}T00:00:00", -i) for i in range(1, 4)]

    assert (
        client.post(
            "/api/transactions/bulk", json={"action": "categorize", "ids": ids, "categoryId": food}
        ).json()["affected"]
        == 3
    )
    assert client.get(f"/api/transactions?categoryId={food}").json()["total"] == 3

    # move to uncategorized, and only real ids count
    r = client.post(
        "/api/transactions/bulk", json={"action": "move", "ids": [ids[0], 999], "categoryId": 0}
    )
    assert r.json()["affected"] == 1
    assert client.get("/api/transactions?uncategorized=true").json()["total"] == 1

    assert (
        client.post(
            "/api/transactions/bulk", json={"action": "categorize", "ids": ids, "categoryId": 999}
        ).status_code
        == 400
    )
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


def test_transaction_delete(client):
    tx = _tx(client, "2026-01-01T00:00:00", -1)
    assert client.delete(f"/api/transactions/{tx}").status_code == 200
    assert client.delete(f"/api/transactions/{tx}").status_code == 404


# -------------------------------------------------------------------------- budgets


def test_budget_put_upsert_and_delete(client):
    g = _group(client, "Expenses", "expense")
    a = _category(client, "A", g)
    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 1, "amount": 1000})
    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 1, "amount": 1500})
    budgets = _snap(client)["budgets"]
    assert len(budgets) == 1 and budgets[0]["amount"] == 1500
    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 1, "amount": 0})
    assert _snap(client)["budgets"] == []
    assert (
        client.put(
            "/api/budgets", json={"categoryId": a, "year": 2026, "month": 13, "amount": 5}
        ).status_code
        == 422
    )


def test_budget_bulk_and_copy_overwrites(client):
    g = _group(client, "Expenses", "expense")
    a = _category(client, "A", g)
    b = _category(client, "B", g)
    client.post(
        "/api/budgets/bulk",
        json={
            "cells": [
                {"categoryId": a, "year": 2026, "month": 1, "amount": 1000},
                {"categoryId": b, "year": 2026, "month": 1, "amount": 2000},
                {"categoryId": a, "year": 2026, "month": 1, "amount": 0},  # deletes a
            ]
        },
    )
    jan = [x for x in _snap(client)["budgets"] if x["month"] == 1]
    assert {x["categoryId"] for x in jan} == {b}

    # month copy overwrites destination (feb had a stale cell)
    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 2, "amount": 777})
    assert (
        client.post(
            "/api/budgets/copy",
            json={"fromYear": 2026, "toYear": 2026, "fromMonth": 1, "toMonth": 2},
        ).json()["copied"]
        == 1
    )
    feb = [x for x in _snap(client)["budgets"] if x["month"] == 2]
    assert len(feb) == 1 and feb[0]["categoryId"] == b and feb[0]["amount"] == 2000

    # year copy
    assert (
        client.post("/api/budgets/copy", json={"fromYear": 2026, "toYear": 2027}).json()["copied"]
        == 2
    )
    assert len([x for x in _snap(client)["budgets"] if x["year"] == 2027]) == 2


def test_budget_copy_validation_and_empty_source(client):
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
    # copying an empty source clears the destination
    g = _group(client, "Expenses", "expense")
    a = _category(client, "A", g)
    client.put("/api/budgets", json={"categoryId": a, "year": 2027, "month": 1, "amount": 500})
    assert (
        client.post(
            "/api/budgets/copy",
            json={"fromYear": 2026, "toYear": 2027, "fromMonth": 1, "toMonth": 1},
        ).json()["copied"]
        == 0
    )
    assert _snap(client)["budgets"] == []


# --------------------------------------------------------------------------- import


def test_import_preview_categorizes_and_flags_errors(client):
    g = _group(client, "Expenses", "expense")
    _category(client, "Groceries", g, "Lenta")
    text = STMT + "garbage line without enough columns\n"
    prev = client.post("/api/import/preview", json={"text": text}).json()
    assert len(prev["rows"]) == 2
    assert prev["rows"][0]["categoryId"] is not None  # matched "Lenta"
    assert prev["rows"][1]["categoryId"] is None
    assert len(prev["errors"]) == 1


def test_import_commit_dedup_within_batch_and_vs_db(client):
    rows = client.post("/api/import/preview", json={"text": STMT}).json()["rows"]

    within = client.post("/api/import/commit", json={"rows": [rows[0], rows[0]]}).json()
    assert within == {"inserted": 1, "skipped": 1}
    assert client.get("/api/transactions").json()["total"] == 1

    both = client.post("/api/import/commit", json={"rows": rows}).json()
    assert both == {"inserted": 1, "skipped": 1}  # rows[0] already there, rows[1] new
    assert client.get("/api/transactions").json()["total"] == 2

    assert client.post("/api/import/commit", json={"rows": rows}).json() == {
        "inserted": 0,
        "skipped": 2,
    }


def test_import_commit_keeps_category(client):
    g = _group(client, "Expenses", "expense")
    cat = _category(client, "Groceries", g)
    rows = client.post("/api/import/preview", json={"text": STMT}).json()["rows"]
    rows[0]["categoryId"] = cat
    client.post("/api/import/commit", json={"rows": rows})
    imported = client.get(f"/api/transactions?categoryId={cat}").json()
    assert imported["total"] == 1 and imported["rows"][0]["source"] == "import"


# ----------------------------------------------------------------------------- auth


def test_api_token_guards_every_route(client, monkeypatch):
    monkeypatch.setenv("MONORI_API_TOKEN", "s3cret")
    hdr = {"Authorization": "Bearer s3cret"}
    # read and write, across routers, all rejected without a valid token
    denied = client.get("/api/snapshot")
    assert denied.status_code == 401 and "token" in denied.json()["detail"].lower()
    assert client.get("/api/groups").status_code == 401
    assert client.post("/api/groups", json={"name": "X", "kind": "expense"}).status_code == 401
    assert client.get("/api/snapshot", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert (
        client.get("/api/snapshot", headers={"Authorization": "s3cret"}).status_code == 401
    )  # no Bearer
    assert client.get("/api/snapshot", headers=hdr).status_code == 200
    assert (
        client.post("/api/groups", json={"name": "X", "kind": "expense"}, headers=hdr).status_code
        == 200
    )
