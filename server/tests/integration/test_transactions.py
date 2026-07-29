import pytest

pytestmark = pytest.mark.integration


def test_transaction_create_variants(api, client):
    g = api.group("Expenses")
    cat = api.category("Food", g)
    manual = api.tx("2026-02-03T10:00:00", -12345, description="Lenta", categoryId=cat)
    row = api.tx_by(manual)
    assert row["source"] == "manual" and row["amount"] == -12345 and row["categoryId"] == cat

    uncat = api.tx("2026-02-04T10:00:00", -1, categoryId=0)
    assert api.tx_by(uncat)["categoryId"] is None

    acct = api.default_account()
    bad = client.post(
        "/api/transactions",
        json={"date": "x", "amount": 1, "accountId": acct, "categoryId": 999},
    )
    assert bad.status_code == 400 and "category" in bad.json()["detail"].lower()

    bad_acct = client.post("/api/transactions", json={"date": "x", "amount": 1, "accountId": 999})
    assert bad_acct.status_code == 400 and "account" in bad_acct.json()["detail"].lower()


def test_transaction_partial_patch_preserves_other_fields(api, client):
    g = api.group("Expenses")
    cat = api.category("Food", g)
    tx = api.tx("2026-02-03T10:00:00", -100, description="Lenta", categoryId=cat, comment="a")
    client.patch(f"/api/transactions/{tx}", json={"comment": "b"})
    row = api.tx_by(tx)
    assert row["comment"] == "b"
    assert row["amount"] == -100 and row["description"] == "Lenta" and row["categoryId"] == cat

    client.patch(
        f"/api/transactions/{tx}",
        json={"amount": -999, "date": "2026-05-05T00:00:00", "description": "X", "categoryId": 0},
    )
    row = api.tx_by(tx)
    assert row["amount"] == -999 and row["date"] == "2026-05-05T00:00:00"
    assert row["categoryId"] is None
    assert client.patch(f"/api/transactions/{tx}", json={"categoryId": 999}).status_code == 400
    assert client.patch("/api/transactions/999", json={"amount": 1}).status_code == 404


def test_transaction_category_must_match_amount_direction(api, client):
    expenses = api.group("Expenses")
    income = api.group("Income", "income")
    food = api.category("Food", expenses)
    salary = api.category("Salary", income)
    account = api.default_account()

    for amount, category in ((-100, salary), (100, food)):
        response = client.post(
            "/api/transactions",
            json={
                "date": "2026-02-03T10:00:00",
                "amount": amount,
                "accountId": account,
                "categoryId": category,
            },
        )
        assert response.status_code == 400

    expense = api.tx("2026-02-03T10:00:00", -100, categoryId=food)
    income_tx = api.tx("2026-02-03T10:00:00", 100, categoryId=salary)
    assert (
        client.patch(f"/api/transactions/{expense}", json={"categoryId": salary}).status_code == 400
    )
    assert (
        client.patch(f"/api/transactions/{income_tx}", json={"categoryId": food}).status_code == 400
    )
    assert client.patch(f"/api/transactions/{expense}", json={"amount": 100}).status_code == 400

    bulk = client.post(
        "/api/transactions/bulk",
        json={"action": "categorize", "ids": [expense, income_tx], "categoryId": food},
    )
    assert bulk.status_code == 400
    assert api.tx_by(expense)["categoryId"] == food
    assert api.tx_by(income_tx)["categoryId"] == salary


def test_transaction_patch_recomputes_hash_for_dedup(api, client):
    """
    Editing date/amount/description must recompute the dedup hash: a statement
    row that matched the old content should stop being a duplicate.
    """
    tx = api.tx("2026-01-05T10:00:00", -10000, description="Lenta")
    assert api.preview(api.statement)[0]["duplicate"] is True

    client.patch(f"/api/transactions/{tx}", json={"description": "Something else"})
    assert api.preview(api.statement)[0]["duplicate"] is False


def test_transaction_list_filters_combined_and_pagination(api, client):
    g = api.group("Expenses")
    inc = api.group("Income", "income")
    food = api.category("Food", g)
    salary = api.category("Salary", inc)
    api.tx("2026-01-05T00:00:00", -100, description="Lenta", categoryId=food)
    api.tx("2026-02-05T00:00:00", -200, description="Pyaterochka", categoryId=food)
    api.tx("2026-03-05T00:00:00", 500000, description="Payroll", categoryId=salary)
    api.tx("2026-03-06T00:00:00", -50, description="Cash")

    assert client.get("/api/transactions").json()["total"] == 4
    assert client.get("/api/transactions?from=2026-02-01&to=2026-02-28").json()["total"] == 1
    assert client.get(f"/api/transactions?categoryId={food}").json()["total"] == 2
    assert client.get("/api/transactions?uncategorized=true").json()["total"] == 1
    assert client.get("/api/transactions?q=PAYROLL").json()["total"] == 1
    assert client.get(f"/api/transactions?categoryId={food}&from=2026-02-01").json()["total"] == 1
    assert (
        client.get(f"/api/transactions?uncategorized=true&categoryId={food}").json()["total"] == 1
    )

    page = client.get("/api/transactions?limit=2&offset=0").json()
    assert len(page["rows"]) == 2 and page["total"] == 4
    assert page["rows"][0]["date"] >= page["rows"][1]["date"]
    tail = client.get("/api/transactions?limit=2&offset=2").json()
    assert tail["rows"][0]["date"] < page["rows"][1]["date"]
    assert client.get("/api/transactions?limit=0").status_code == 422
    assert client.get("/api/transactions?limit=99999").status_code == 422


def test_transaction_to_filter_covers_the_whole_boundary_day(api, client):
    api.tx("2026-02-28T23:59:59", -100)  # late on the boundary day
    api.tx("2026-03-01T00:00:00", -200)  # next day
    assert client.get("/api/transactions?to=2026-02-28").json()["total"] == 1
    assert client.get("/api/transactions?from=2026-02-28&to=2026-02-28").json()["total"] == 1
    assert client.get("/api/transactions?from=2026-03-01").json()["total"] == 1


def test_transaction_bulk_actions(api, client):
    g = api.group("Expenses")
    food = api.category("Food", g)
    ids = [api.tx(f"2026-01-0{i}T00:00:00", -i) for i in range(1, 4)]

    r = client.post(
        "/api/transactions/bulk", json={"action": "categorize", "ids": ids, "categoryId": food}
    )
    assert r.json()["affected"] == 3
    assert client.get(f"/api/transactions?categoryId={food}").json()["total"] == 3

    moved = client.post(
        "/api/transactions/bulk", json={"action": "move", "ids": [ids[0], 999], "categoryId": 0}
    )
    assert moved.json()["affected"] == 1
    assert client.get("/api/transactions?uncategorized=true").json()["total"] == 1

    bad_cat = client.post(
        "/api/transactions/bulk", json={"action": "categorize", "ids": ids, "categoryId": 999}
    )
    assert bad_cat.status_code == 400
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


def test_transaction_delete(api, client):
    tx = api.tx("2026-01-01T00:00:00", -1)
    assert client.delete(f"/api/transactions/{tx}").status_code == 200
    assert client.delete(f"/api/transactions/{tx}").status_code == 404


def test_splits_are_atomic_and_visible_in_snapshot(api, client):
    expenses = api.group("Expenses")
    groceries = api.category("Groceries", expenses)
    household = api.category("Household", expenses)
    tx = api.tx("2026-01-01T00:00:00", -10_00, description="Mixed receipt")

    response = client.put(
        f"/api/transactions/{tx}/splits",
        json={
            "parts": [
                {"categoryId": groceries, "amount": -6_01, "comment": "food"},
                {"categoryId": household, "amount": -3_99, "comment": "soap"},
            ]
        },
    )
    assert response.status_code == 200
    row = api.tx_by(tx)
    assert row["categoryId"] is None
    assert sum(part["amount"] for part in row["splits"]) == row["amount"]
    assert [part["comment"] for part in row["splits"]] == ["food", "soap"]
    assert client.get(f"/api/transactions?categoryId={groceries}").json()["total"] == 1
    assert client.get("/api/transactions?uncategorized=true").json()["total"] == 0

    bad = client.put(
        f"/api/transactions/{tx}/splits",
        json={
            "parts": [
                {"categoryId": groceries, "amount": -5_00},
                {"categoryId": household, "amount": -4_99},
            ]
        },
    )
    assert bad.status_code == 400
    assert api.tx_by(tx)["splits"] == row["splits"]
    assert client.patch(f"/api/transactions/{tx}", json={"amount": -11_00}).status_code == 400

    assert client.put(f"/api/transactions/{tx}/splits", json={"parts": []}).status_code == 200
    assert api.tx_by(tx)["splits"] == []


def test_transaction_split_validates_owner_kind_and_sign(api, client):
    expenses = api.group("Expenses")
    income = api.group("Income", "income")
    food = api.category("Food", expenses)
    salary = api.category("Salary", income)
    tx = api.tx("2026-01-01T00:00:00", -10_00)

    for parts in (
        [{"categoryId": food, "amount": -10_00}],
        [{"categoryId": food, "amount": -5_00}, {"categoryId": salary, "amount": -5_00}],
        [{"categoryId": food, "amount": -11_00}, {"categoryId": food, "amount": 1_00}],
    ):
        assert (
            client.put(f"/api/transactions/{tx}/splits", json={"parts": parts}).status_code == 400
        )


def test_hidden_transaction_disappears_from_list_and_snapshot(api, client):
    keep = api.tx("2026-01-01T00:00:00", -100, description="Keep")
    junk = api.tx("2026-01-02T00:00:00", -200, description="Junk")

    assert client.patch(f"/api/transactions/{junk}", json={"hidden": True}).status_code == 200

    listed = client.get("/api/transactions").json()
    assert listed["total"] == 1
    assert [r["id"] for r in listed["rows"]] == [keep]

    snap = api.snapshot()
    assert [t["id"] for t in snap["transactions"]] == [keep]
    assert snap["transactionsTotal"] == 1

    hidden = client.get("/api/transactions?hidden=true").json()
    assert hidden["total"] == 1
    assert [r["id"] for r in hidden["rows"]] == [junk]
    assert hidden["rows"][0]["hidden"] is True

    assert client.patch(f"/api/transactions/{junk}", json={"hidden": False}).status_code == 200
    assert client.get("/api/transactions").json()["total"] == 2
    assert client.get("/api/transactions?hidden=true").json()["total"] == 0


def test_patch_without_hidden_keeps_the_flag(api, client):
    tx = api.tx("2026-01-01T00:00:00", -100, description="Junk")
    client.patch(f"/api/transactions/{tx}", json={"hidden": True})
    client.patch(f"/api/transactions/{tx}", json={"comment": "still junk"})
    hidden = client.get("/api/transactions?hidden=true").json()
    assert hidden["total"] == 1 and hidden["rows"][0]["comment"] == "still junk"


def test_hidden_transaction_still_blocks_reimport(api, client):
    tx = api.tx("2026-01-05T10:00:00", -10000, description="Lenta")
    assert client.patch(f"/api/transactions/{tx}", json={"hidden": True}).status_code == 200
    assert client.get("/api/transactions").json()["total"] == 0
    assert client.get("/api/transactions?hidden=true").json()["total"] == 1
    # the row is invisible everywhere, but a re-sync of the same statement
    # line must still see it as a duplicate — otherwise hiding is undone by
    # the next bank sync
    assert api.preview(api.statement)[0]["duplicate"] is True
