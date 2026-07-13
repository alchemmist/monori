import pytest

pytestmark = pytest.mark.integration


def test_category_create_sort_and_conflicts(api, client):
    g = api.group("Expenses")
    a = api.category("A", g)
    b = api.category("B", g)
    assert [c["sort"] for c in api.snapshot()["categories"]] == [1, 2]
    assert client.post("/api/categories", json={"name": "A", "groupId": g}).status_code == 409
    assert client.post("/api/categories", json={"name": "X", "groupId": 999}).status_code == 400
    assert client.post("/api/categories", json={"name": "", "groupId": g}).status_code == 422
    assert a != b


def test_category_patch_move_group_and_name(api, client):
    g1 = api.group("Expenses", "expense")
    g2 = api.group("Income", "income")
    a = api.category("A", g1)
    api.category("B", g1)
    assert client.patch(f"/api/categories/{a}", json={"groupId": g2}).status_code == 200
    assert api.cat(a)["groupId"] == g2
    assert client.patch(f"/api/categories/{a}", json={"groupId": 999}).status_code == 400
    assert client.patch(f"/api/categories/{a}", json={"name": "B"}).status_code == 409
    assert client.patch("/api/categories/999", json={"name": "z"}).status_code == 404
    assert client.patch(f"/api/categories/{a}", json={"keywords": "x|y"}).status_code == 200
    assert api.cat(a)["keywords"] == "x|y"


def test_category_reorder_and_archive_roundtrip(api, client):
    g = api.group("Expenses")
    a = api.category("A", g)
    b = api.category("B", g)
    assert client.post("/api/categories/reorder", json={"ids": [b, a]}).status_code == 200
    assert [c["id"] for c in api.snapshot()["categories"]] == [b, a]
    assert client.post("/api/categories/reorder", json={"ids": [a]}).status_code == 400

    assert client.patch(f"/api/categories/{a}", json={"archived": True}).status_code == 200
    assert api.cat(a)["archived"] is True
    client.patch(f"/api/categories/{a}", json={"archived": False})
    assert api.cat(a)["archived"] is False


def test_category_delete_reassign_never_shifts(api, client):
    g = api.group("Expenses")
    a = api.category("A", g)
    b = api.category("B", g)
    tx = api.tx("2026-01-01T00:00:00", -500, categoryId=a)
    client.put("/api/budgets", json={"categoryId": a, "year": 2026, "month": 1, "amount": 1000})
    client.put("/api/budgets", json={"categoryId": b, "year": 2026, "month": 1, "amount": 2000})

    assert client.delete(f"/api/categories/{a}?reassignTo=999").status_code == 400
    assert client.delete(f"/api/categories/{a}?reassignTo={b}").status_code == 200
    snap = api.snapshot()
    assert api.tx_by(tx)["categoryId"] == b
    assert {x["categoryId"]: x["amount"] for x in snap["budgets"]} == {b: 2000}


def test_category_delete_without_reassign_uncategorizes(api, client):
    g = api.group("Expenses")
    a = api.category("A", g)
    tx = api.tx("2026-01-01T00:00:00", -500, categoryId=a)
    assert client.delete(f"/api/categories/{a}").status_code == 200
    assert api.tx_by(tx)["categoryId"] is None
    assert client.delete("/api/categories/999").status_code == 404


def test_category_merge_moves_tx_and_unions_keywords(api, client):
    g = api.group("Expenses")
    src = api.category("Coffee", g, "cofix|STARBUCKS")
    dst = api.category("Cafe", g, "starbucks|shokoladnitsa")
    tx = api.tx("2026-01-01T00:00:00", -500, categoryId=src)
    client.put("/api/budgets", json={"categoryId": src, "year": 2026, "month": 1, "amount": 900})

    assert client.post(f"/api/categories/{src}/merge", json={"into": src}).status_code == 400
    assert client.post(f"/api/categories/{src}/merge", json={"into": 999}).status_code == 400
    assert client.post("/api/categories/999/merge", json={"into": dst}).status_code == 404

    assert client.post(f"/api/categories/{src}/merge", json={"into": dst}).status_code == 200
    snap = api.snapshot()
    assert [c["id"] for c in snap["categories"]] == [dst]
    assert api.tx_by(tx)["categoryId"] == dst
    assert api.cat(dst)["keywords"].split("|") == ["starbucks", "shokoladnitsa", "cofix"]
    assert snap["budgets"] == []


def test_merge_with_empty_keywords(api, client):
    g = api.group("Expenses")
    src = api.category("Src", g, "")
    dst = api.category("Dst", g, "coffee")
    client.post(f"/api/categories/{src}/merge", json={"into": dst})
    assert api.cat(dst)["keywords"] == "coffee"

    src2 = api.category("Src2", g, "tea")
    dst2 = api.category("Dst2", g, "")
    client.post(f"/api/categories/{src2}/merge", json={"into": dst2})
    assert api.cat(dst2)["keywords"] == "tea"
