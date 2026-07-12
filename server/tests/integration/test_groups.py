import pytest

pytestmark = pytest.mark.integration


def test_groups_full_lifecycle(api, client):
    assert client.get("/api/groups").json() == []
    exp = api.group("Expenses", "expense")
    api.group("Income", "income")
    groups = client.get("/api/groups").json()
    assert [g["name"] for g in groups] == ["Expenses", "Income"]
    assert [g["sort"] for g in groups] == [1, 2]
    assert groups[0]["kind"] == "expense"

    r = client.patch(f"/api/groups/{exp}", json={"name": "Fixed", "kind": "income"})
    assert r.status_code == 200
    g = next(x for x in client.get("/api/groups").json() if x["id"] == exp)
    assert g["name"] == "Fixed" and g["kind"] == "income"


def test_group_validation_and_conflicts(api, client):
    exp = api.group("Expenses", "expense")
    assert (
        client.post("/api/groups", json={"name": "Expenses", "kind": "expense"}).status_code == 409
    )
    assert client.post("/api/groups", json={"name": "Bad", "kind": "nope"}).status_code == 400
    assert client.post("/api/groups", json={"name": "", "kind": "expense"}).status_code == 422
    api.group("Income", "income")
    assert client.patch(f"/api/groups/{exp}", json={"name": "Income"}).status_code == 409
    assert client.patch(f"/api/groups/{exp}", json={"kind": "bad"}).status_code == 400
    assert client.patch("/api/groups/999", json={"name": "x"}).status_code == 404


def test_group_reorder_persists_and_validates(api, client):
    a = api.group("A")
    b = api.group("B")
    c = api.group("C")
    assert client.post("/api/groups/reorder", json={"ids": [c, a, b]}).status_code == 200
    groups = client.get("/api/groups").json()
    assert [g["id"] for g in groups] == [c, a, b]
    assert [g["sort"] for g in groups] == [1, 2, 3]
    assert client.post("/api/groups/reorder", json={"ids": [a, b]}).status_code == 400
    assert client.post("/api/groups/reorder", json={"ids": [a, b, c, 999]}).status_code == 400
    assert client.post("/api/groups/reorder", json={"ids": [a, a, b]}).status_code == 400


def test_group_delete_guards_non_empty(api, client):
    exp = api.group("Expenses", "expense")
    api.category("Groceries", exp)
    assert client.delete(f"/api/groups/{exp}").status_code == 409
    assert client.delete("/api/groups/999").status_code == 404
    empty = api.group("Empty", "expense")
    assert client.delete(f"/api/groups/{empty}").status_code == 200
    assert empty not in [g["id"] for g in client.get("/api/groups").json()]
