from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from pydantic import TypeAdapter

from monori.server.app.deps import IdResponse
from monori.server.app.routers.imports import (
    MAX_STATEMENT_TEXT,
    DuplicatesResponse,
    ImportCommitResponse,
    ImportPreviewResponse,
    ImportRowResponse,
)
from monori.server.app.routers.transactions import TransactionListResponse
from monori.server.tests.conftest import AccountOptions, Api, TransactionOptions

pytestmark = pytest.mark.integration


def counts(response: Response) -> dict[str, int]:
    body = TypeAdapter(ImportCommitResponse).validate_python(response.json())
    return {"inserted": body.inserted, "skipped": body.skipped}


def commit(client: TestClient, api: Api, rows: Sequence[ImportRowResponse]) -> dict[str, int]:
    payload = TypeAdapter(list[ImportRowResponse]).dump_python(list(rows), mode="json")
    return counts(
        client.post(
            "/api/import/commit",
            json={"accountId": api.default_account(), "rows": payload},
        ),
    )


def test_import_preview_categorizes_and_flags_errors(api: Api, client: TestClient) -> None:
    g = api.group("Expenses")
    api.category("Groceries", g, "Lenta")
    text = api.statement + "garbage line without enough columns\n"
    prev = TypeAdapter(ImportPreviewResponse).validate_python(
        client.post("/api/import/preview", json={"text": text}).json(),
    )
    assert len(prev.rows) == 2
    assert prev.rows[0].category_id is not None
    assert prev.rows[1].category_id is None
    assert len(prev.errors) == 1


def test_preview_routes_each_card_and_commit_accepts_mixed_accounts(
    api: Api,
    client: TestClient,
) -> None:
    first = api.default_account()
    second = api.account("Second card", AccountOptions(card_tails=["2947"]))
    client.patch(f"/api/accounts/{first}", json={"cardTails": ["1111"]})

    def row(card: str, amount: str, description: str, day: int) -> str:
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
                ],
            )
            + "\n"
        )

    text = (
        row("*1111", "-100,00", "First", 5)
        + row("*2947", "-200,00", "Second", 6)
        + row("*9999", "-300,00", "Unknown", 7)
    )
    preview = TypeAdapter(ImportPreviewResponse).validate_python(
        client.post("/api/import/preview", json={"text": text}).json(),
    )
    rows = preview.rows
    assert [row.account_id for row in rows] == [first, second, None]

    rows[2].account_id = first
    payload = TypeAdapter(list[ImportRowResponse]).dump_python(rows, mode="json")
    r = client.post("/api/import/commit", json={"rows": payload})
    assert counts(r) == {"inserted": 3, "skipped": 0}
    tx = (
        TypeAdapter(TransactionListResponse)
        .validate_python(client.get("/api/transactions?limit=10").json())
        .rows
    )
    assert {row.description: row.account_id for row in tx} == {
        "First": first,
        "Second": second,
        "Unknown": first,
    }


def test_duplicate_check_uses_the_account_selected_for_each_row(
    api: Api,
    client: TestClient,
) -> None:
    other = api.account("Other")
    rows = api.preview(api.statement)
    api.tx(
        rows[0].date,
        rows[0].amount,
        TransactionOptions(account_id=other, description=rows[0].description),
    )
    rows[0].account_id = other

    payload = TypeAdapter(list[ImportRowResponse]).dump_python(rows, mode="json")
    checked = TypeAdapter(DuplicatesResponse).validate_python(
        client.post("/api/import/duplicates", json={"rows": payload}).json(),
    )
    assert checked.duplicates == [True, False]


def test_import_commit_double_submit_is_idempotent(api: Api, client: TestClient) -> None:
    rows = api.preview(api.statement)
    assert commit(client, api, rows) == {"inserted": 2, "skipped": 0}
    assert commit(client, api, rows) == {"inserted": 0, "skipped": 2}
    transactions = TypeAdapter(TransactionListResponse).validate_python(
        client.get("/api/transactions").json(),
    )
    assert transactions.total == 2


def test_import_commit_skips_only_the_first_n_already_stored(api: Api, client: TestClient) -> None:
    """
    Skip as many identical rows as already exist in the DB, insert the rest —.

    a fresh statement's own repeats are legitimate, only re-imports are skipped.
    """
    r0 = api.preview(api.statement)[0]

    assert commit(client, api, [r0, r0, r0]) == {"inserted": 3, "skipped": 0}
    transactions = TypeAdapter(TransactionListResponse).validate_python(
        client.get("/api/transactions").json(),
    )
    assert transactions.total == 3

    assert commit(client, api, [r0, r0, r0]) == {"inserted": 0, "skipped": 3}

    assert commit(client, api, [r0] * 5) == {"inserted": 2, "skipped": 3}
    assert client.get("/api/transactions").json()["total"] == 5


def test_import_commit_keeps_category(api: Api, client: TestClient) -> None:
    g = api.group("Expenses")
    cat = api.category("Groceries", g)
    rows = api.preview(api.statement)
    rows[0].category_id = cat
    payload = TypeAdapter(list[ImportRowResponse]).dump_python(rows, mode="json")
    client.post("/api/import/commit", json={"accountId": api.default_account(), "rows": payload})
    imported = TypeAdapter(TransactionListResponse).validate_python(
        client.get(f"/api/transactions?categoryId={cat}").json(),
    )
    assert imported.total == 1
    assert imported.rows[0].source == "import"


def test_import_commit_accepts_goal_category(api: Api, client: TestClient) -> None:
    goals = api.group("Goals", kind="goal")
    created = client.post(
        "/api/categories",
        json={"name": "Camera", "groupId": goals, "goalTarget": 100_000},
    )
    created_category = TypeAdapter(IdResponse).validate_python(created.json())
    assert created_category.id is not None
    goal = created_category.id
    rows = api.preview(api.statement)
    rows[0].category_id = goal

    response = client.post(
        "/api/import/commit",
        json={
            "accountId": api.default_account(),
            "rows": TypeAdapter(list[ImportRowResponse]).dump_python(rows, mode="json"),
        },
    )

    assert response.status_code == 200, response.text
    imported = TypeAdapter(TransactionListResponse).validate_python(
        client.get(f"/api/transactions?categoryId={goal}").json(),
    )
    assert imported.total == 1


def test_import_commit_rejects_category_with_the_wrong_direction(
    api: Api,
    client: TestClient,
) -> None:
    expenses = api.group("Expenses")
    income = api.group("Income", "income")
    food = api.category("Groceries", expenses)
    salary = api.category("Salary", income)
    rows = api.preview(api.statement)

    rows[0].category_id = salary
    payload = TypeAdapter(list[ImportRowResponse]).dump_python(rows, mode="json")
    bad_expense = client.post(
        "/api/import/commit",
        json={"accountId": api.default_account(), "rows": payload},
    )
    assert bad_expense.status_code == 400

    rows = api.preview(api.statement)
    rows[1].amount = 100
    rows[1].category_id = food
    payload = TypeAdapter(list[ImportRowResponse]).dump_python(rows, mode="json")
    bad_income = client.post(
        "/api/import/commit",
        json={"accountId": api.default_account(), "rows": payload},
    )
    assert bad_income.status_code == 400


def test_commit_rejects_unknown_account(client: TestClient) -> None:
    r = client.post("/api/import/commit", json={"accountId": 999, "rows": []})
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown account"


def test_preview_rejects_oversized_statement(api: Api, client: TestClient) -> None:
    big = "x" * (MAX_STATEMENT_TEXT + 1)
    r = client.post("/api/import/preview", json={"text": big, "accountId": api.default_account()})
    assert r.status_code == 413
    assert r.json()["detail"] == "statement is too large"


def test_import_preview_never_proposes_a_wrong_direction_category(
    api: Api,
) -> None:
    """
    The refund fallback in the categorizer would happily file "Lenta +100" into.

    Groceries — but the commit rejects wrong-direction categories, so a preview.
    proposing one would make the whole statement unimportable.
    """
    expenses = api.group("Expenses")
    api.category("Groceries", expenses, keywords="lenta")
    refund = api.statement.splitlines()[0].replace("-100,00", "100,00") + "\n"
    rows = api.preview(refund)
    assert rows[0].amount > 0
    assert rows[0].category_id is None
