import pytest

pytestmark = pytest.mark.integration


def counts(response):
    body = response.json() if hasattr(response, "json") else response
    return {"inserted": body["inserted"], "skipped": body["skipped"]}


def commit(client, api, rows):
    return counts(
        client.post("/api/import/commit", json={"accountId": api.default_account(), "rows": rows})
    )


def test_import_preview_categorizes_and_flags_errors(api, client):
    g = api.group("Expenses")
    api.category("Groceries", g, "Lenta")
    text = api.statement + "garbage line without enough columns\n"
    prev = client.post("/api/import/preview", json={"text": text}).json()
    assert len(prev["rows"]) == 2
    assert prev["rows"][0]["categoryId"] is not None
    assert prev["rows"][1]["categoryId"] is None
    assert len(prev["errors"]) == 1


def test_preview_routes_each_card_and_commit_accepts_mixed_accounts(api, client):
    first = api.default_account()
    second = api.account("Second card", cardTails=["2947"])
    client.patch(f"/api/accounts/{first}", json={"cardTails": ["1111"]})

    def row(card, amount, description, day):
        return (
            "\t".join(
                [
                    f"0{day}.01.2026 10:00:00",
                    f"0{day}.01.2026",
                    card,
                    "OK",
                    amount,
                    "RUB",
                    amount,
                    "RUB",
                    "",
                    "Super",
                    "5411",
                    description,
                    "0",
                    "0",
                    amount,
                ]
            )
            + "\n"
        )

    text = (
        row("*1111", "-100,00", "First", 5)
        + row("*2947", "-200,00", "Second", 6)
        + row("*9999", "-300,00", "Unknown", 7)
    )
    rows = client.post("/api/import/preview", json={"text": text}).json()["rows"]
    assert [row["accountId"] for row in rows] == [first, second, None]

    rows[2]["accountId"] = first
    r = client.post("/api/import/commit", json={"rows": rows})
    assert counts(r) == {"inserted": 3, "skipped": 0}
    tx = client.get("/api/transactions?limit=10").json()["rows"]
    assert {row["description"]: row["accountId"] for row in tx} == {
        "First": first,
        "Second": second,
        "Unknown": first,
    }


def test_duplicate_check_uses_the_account_selected_for_each_row(api, client):
    other = api.account("Other")
    rows = api.preview(api.statement)
    api.tx(rows[0]["date"], rows[0]["amount"], accountId=other, description=rows[0]["description"])
    rows[0]["accountId"] = other

    checked = client.post("/api/import/duplicates", json={"rows": rows}).json()
    assert checked["duplicates"] == [True, False]


def test_import_commit_double_submit_is_idempotent(api, client):
    rows = api.preview(api.statement)
    assert commit(client, api, rows) == {"inserted": 2, "skipped": 0}
    assert commit(client, api, rows) == {"inserted": 0, "skipped": 2}
    assert client.get("/api/transactions").json()["total"] == 2


def test_import_commit_skips_only_the_first_n_already_stored(api, client):
    """
    Skip as many identical rows as already exist in the DB, insert the rest —
    a fresh statement's own repeats are legitimate, only re-imports are skipped.
    """
    r0 = api.preview(api.statement)[0]

    # fresh DB: three identical rows are all genuinely new
    assert commit(client, api, [r0, r0, r0]) == {"inserted": 3, "skipped": 0}
    assert client.get("/api/transactions").json()["total"] == 3

    # DB now holds 3; the same three are all skipped
    assert commit(client, api, [r0, r0, r0]) == {"inserted": 0, "skipped": 3}

    # DB holds 3; five identical -> two beyond the stored three are inserted
    assert commit(client, api, [r0] * 5) == {"inserted": 2, "skipped": 3}
    assert client.get("/api/transactions").json()["total"] == 5


def test_import_commit_keeps_category(api, client):
    g = api.group("Expenses")
    cat = api.category("Groceries", g)
    rows = api.preview(api.statement)
    rows[0]["categoryId"] = cat
    client.post("/api/import/commit", json={"accountId": api.default_account(), "rows": rows})
    imported = client.get(f"/api/transactions?categoryId={cat}").json()
    assert imported["total"] == 1 and imported["rows"][0]["source"] == "import"


def test_import_commit_rejects_category_with_the_wrong_direction(api, client):
    expenses = api.group("Expenses")
    income = api.group("Income", "income")
    food = api.category("Groceries", expenses)
    salary = api.category("Salary", income)
    rows = api.preview(api.statement)

    rows[0]["categoryId"] = salary
    bad_expense = client.post(
        "/api/import/commit", json={"accountId": api.default_account(), "rows": rows}
    )
    assert bad_expense.status_code == 400

    rows = api.preview(api.statement)
    rows[1]["amount"] = 100
    rows[1]["categoryId"] = food
    bad_income = client.post(
        "/api/import/commit", json={"accountId": api.default_account(), "rows": rows}
    )
    assert bad_income.status_code == 400


def test_commit_rejects_unknown_account(client):
    r = client.post("/api/import/commit", json={"accountId": 999, "rows": []})
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown account"


def test_preview_rejects_oversized_statement(api, client):
    from app.routers.imports import MAX_STATEMENT_TEXT

    big = "x" * (MAX_STATEMENT_TEXT + 1)
    r = client.post("/api/import/preview", json={"text": big, "accountId": api.default_account()})
    assert r.status_code == 413
    assert r.json()["detail"] == "statement is too large"


def test_import_preview_never_proposes_a_wrong_direction_category(api, client):
    """
    The refund fallback in the categorizer would happily file "Lenta +100" into
    Groceries — but the commit rejects wrong-direction categories, so a preview
    proposing one would make the whole statement unimportable.
    """
    expenses = api.group("Expenses")
    api.category("Groceries", expenses, keywords="lenta")
    refund = api.statement.splitlines()[0].replace("-100,00", "100,00") + "\n"
    rows = api.preview(refund)
    assert rows[0]["amount"] > 0
    assert rows[0]["categoryId"] is None
