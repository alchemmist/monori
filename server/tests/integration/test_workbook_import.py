import json
from io import BytesIO

import httpx2
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pydantic import TypeAdapter

from app.deps import IdResponse, SnapshotResponse
from tests.conftest import Api, login_as

pytestmark = pytest.mark.integration


def _required_id(response: httpx2.Response) -> int:
    body = TypeAdapter(IdResponse).validate_python(response.json())
    assert body.id is not None
    return body.id


def _seed(api: Api, client: TestClient) -> int:
    g_out = api.group("Daily Expenses")
    g_in = api.group("Inflow", kind="income")
    cat = api.category("Groceries", g_out, keywords="lenta|okey")
    salary = api.category("Salary", g_in)
    acct = api.account("Card")
    api.tx("2026-01-05T10:00:00", -12550, accountId=acct, categoryId=cat, description="Lenta")
    api.tx("2026-01-10T09:00:00", 500000, accountId=acct, categoryId=salary, description="Pay")
    api.tx("2026-02-01T12:00:00", -700, accountId=acct, description="Okey market")
    client.put("/api/budgets", json={"categoryId": cat, "year": 2026, "month": 1, "amount": 20000})
    client.put("/api/budgets", json={"categoryId": cat, "year": 2026, "month": 2, "amount": 30000})
    return acct


def _export_bytes(client: TestClient) -> bytes:
    r = client.get("/api/export/xlsx")
    assert r.status_code == 200
    return r.content


def _upload(
    client: TestClient,
    path: str,
    data: bytes,
    extra: dict[str, str] | None = None,
) -> httpx2.Response:
    files = {"file": ("book.xlsx", data, "application/octet-stream")}
    return client.post(path, files=files, data=extra or {})


def test_workbook_preview_summarizes(api: Api, client: TestClient) -> None:
    _seed(api, client)
    data = _export_bytes(client)
    r = _upload(client, "/api/import/workbook/preview", data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["groups"] == 2
    assert body["categories"] == 2
    assert body["transactions"] == 3
    assert body["transactionsByYear"] == {"2026": 3}
    assert body["budgetCells"] == 2
    assert body["accountSlots"] == [
        {"key": "RUB:Card", "marker": "Card", "currency": "RUB", "transactions": 3},
    ]
    assert body["budgetConflicts"] == 2
    assert body["errors"] == []


def test_workbook_preview_reports_no_conflicts_for_fresh_user(api: Api, client: TestClient) -> None:
    _seed(api, client)
    data = _export_bytes(client)
    client.headers.update(login_as(client, "fresh@example.com"))
    r = _upload(client, "/api/import/workbook/preview", data)
    assert r.status_code == 200, r.text
    assert r.json()["budgetConflicts"] == 0


def test_workbook_preview_rejects_garbage(client: TestClient) -> None:
    r = _upload(client, "/api/import/workbook/preview", b"not an xlsx")
    assert r.status_code == 400
    assert "workbook" in r.json()["detail"]


def test_workbook_commit_requires_full_mapping(api: Api, client: TestClient) -> None:
    _seed(api, client)
    data = _export_bytes(client)
    r = _upload(client, "/api/import/workbook/commit", data, {"mapping": "{}"})
    assert r.status_code == 400
    assert "unmapped" in r.json()["detail"]


def test_workbook_commit_rejects_foreign_account(api: Api, client: TestClient) -> None:
    _seed(api, client)
    data = _export_bytes(client)
    other = login_as(client, "other@example.com")
    r = client.post(
        "/api/import/workbook/commit",
        files={"file": ("book.xlsx", data, "application/octet-stream")},
        data={"mapping": json.dumps({"RUB:Card": 1})},
        headers=other,
    )
    assert r.status_code == 400


def test_workbook_roundtrip_into_fresh_user(api: Api, client: TestClient) -> None:
    _seed(api, client)
    data = _export_bytes(client)

    client.headers.update(login_as(client, "fresh@example.com"))
    r = client.post(
        "/api/accounts",
        json={
            "name": "Imported card",
            "type": "cash",
            "icon": "wallet",
            "color": "#5b6472",
            "currency": "RUB",
            "openingBalance": 0,
            "bankRef": "",
        },
    )
    assert r.status_code == 200
    target = _required_id(r)

    r = client.post(
        "/api/import/workbook/commit",
        files={"file": ("book.xlsx", data, "application/octet-stream")},
        data={"mapping": json.dumps({"RUB:Card": target})},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["groupsCreated"] == 2
    assert result["categoriesCreated"] == 2
    assert result["inserted"] == 3
    assert result["skipped"] == 0
    assert result["budgetsWritten"] == 2

    snap = TypeAdapter(SnapshotResponse).validate_python(client.get("/api/snapshot").json())
    assert {group.name for group in snap.groups} >= {"Daily Expenses", "Inflow"}
    kinds = {group.name: group.kind for group in snap.groups}
    assert kinds["Inflow"] == "income"
    assert kinds["Daily Expenses"] == "expense"
    cats = {category.name: category for category in snap.categories}
    assert cats["Groceries"].keywords == "lenta|okey"
    txs = sorted(snap.transactions, key=lambda transaction: transaction.date)
    assert [
        (transaction.date, transaction.amount, transaction.description) for transaction in txs
    ] == [
        ("2026-01-05T10:00:00", -12550, "Lenta"),
        ("2026-01-10T09:00:00", 500000, "Pay"),
        ("2026-02-01T12:00:00", -700, "Okey market"),
    ]
    assert txs[0].categoryId == cats["Groceries"].id
    assert txs[1].categoryId == cats["Salary"].id
    assert txs[2].categoryId is None
    budgets = {budget.month: budget.amount for budget in snap.budgets}
    assert budgets == {1: 20000, 2: 30000}


def test_workbook_reimport_is_idempotent(api: Api, client: TestClient) -> None:
    _seed(api, client)
    data = _export_bytes(client)
    client.headers.update(login_as(client, "again@example.com"))
    target = _required_id(
        client.post(
            "/api/accounts",
            json={
                "name": "T",
                "type": "cash",
                "icon": "wallet",
                "color": "#5b6472",
                "currency": "RUB",
                "openingBalance": 0,
                "bankRef": "",
            },
        ),
    )
    payload = {"mapping": json.dumps({"RUB:Card": target})}
    files = {"file": ("book.xlsx", data, "application/octet-stream")}
    first = client.post("/api/import/workbook/commit", files=files, data=payload).json()
    second = client.post("/api/import/workbook/commit", files=files, data=payload).json()
    assert first["inserted"] == 3
    assert second["inserted"] == 0
    assert second["skipped"] == 3
    assert second["groupsCreated"] == 0
    assert second["categoriesCreated"] == 0
    snap = TypeAdapter(SnapshotResponse).validate_python(client.get("/api/snapshot").json())
    assert len(snap.transactions) == 3


def test_workbook_budget_policy_skip(api: Api, client: TestClient) -> None:
    _seed(api, client)
    data = _export_bytes(client)
    client.headers.update(login_as(client, "policy@example.com"))
    target = _required_id(
        client.post(
            "/api/accounts",
            json={
                "name": "T",
                "type": "cash",
                "icon": "wallet",
                "color": "#5b6472",
                "currency": "RUB",
                "openingBalance": 0,
                "bankRef": "",
            },
        ),
    )
    files = {"file": ("book.xlsx", data, "application/octet-stream")}
    r = client.post(
        "/api/import/workbook/commit",
        files=files,
        data={"mapping": json.dumps({"RUB:Card": target})},
    )
    assert r.status_code == 200
    snap = TypeAdapter(SnapshotResponse).validate_python(client.get("/api/snapshot").json())
    groceries = next(category for category in snap.categories if category.name == "Groceries")
    client.put(
        "/api/budgets",
        json={"categoryId": groceries.id, "year": 2026, "month": 1, "amount": 777},
    )
    r = client.post(
        "/api/import/workbook/commit",
        files=files,
        data={"mapping": json.dumps({"RUB:Card": target}), "budgetPolicy": "skip"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["budgetsSkipped"] == 2
    assert body["budgetsWritten"] == 0
    snap = TypeAdapter(SnapshotResponse).validate_python(client.get("/api/snapshot").json())
    jan = next(budget for budget in snap.budgets if budget.month == 1)
    assert jan.amount == 777
    r = client.post(
        "/api/import/workbook/commit",
        files=files,
        data={"mapping": json.dumps({"RUB:Card": target}), "budgetPolicy": "overwrite"},
    )
    assert r.json()["budgetsWritten"] == 2
    snap = TypeAdapter(SnapshotResponse).validate_python(client.get("/api/snapshot").json())
    jan = next(budget for budget in snap.budgets if budget.month == 1)
    assert jan.amount == 20000


def test_workbook_commit_bad_policy_and_mapping(api: Api, client: TestClient) -> None:
    _seed(api, client)
    data = _export_bytes(client)
    r = _upload(
        client,
        "/api/import/workbook/commit",
        data,
        {"mapping": "{}", "budgetPolicy": "merge"},
    )
    assert r.status_code == 400
    assert "budgetPolicy" in r.json()["detail"]
    r = _upload(client, "/api/import/workbook/commit", data, {"mapping": "not json"})
    assert r.status_code == 400


def test_workbook_import_lands_as_rollbackable_batch(api: Api, client: TestClient) -> None:
    _seed(api, client)
    data = _export_bytes(client)
    client.headers.update(login_as(client, "batch@example.com"))
    target = _required_id(
        client.post(
            "/api/accounts",
            json={
                "name": "T",
                "type": "cash",
                "icon": "wallet",
                "color": "#5b6472",
                "currency": "RUB",
                "openingBalance": 0,
                "bankRef": "",
            },
        ),
    )
    r = client.post(
        "/api/import/workbook/commit",
        files={"file": ("book.xlsx", data, "application/octet-stream")},
        data={"mapping": json.dumps({"RUB:Card": target})},
    )
    batch = r.json()["batches"][0]
    assert batch["accountId"] == target
    assert batch["inserted"] == 3


def test_workbook_upload_guards(client: TestClient) -> None:
    r = client.post(
        "/api/import/workbook/preview",
        files={"file": ("book.xlsx", b"", "application/octet-stream")},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "empty upload"

    r = client.post(
        "/api/import/workbook/preview",
        files={"file": ("book.xlsx", b"x" * (30 * 1024 * 1024), "application/octet-stream")},
    )
    assert r.status_code == 400
    assert r.json()["detail"] != "workbook is too large"


def _mixed_currency_book() -> bytes:
    """
    One card carrying both RUB and USD rows — the shape a foreign-currency.

    balance leaves in a bank export.
    """
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Transactions"
    ws.append(
        [
            "Operation date",
            "Card",
            "Status",
            "Operation amount",
            "Transaction currency",
            "Description",
        ],
    )
    ws.append(["2026-01-05 10:00:00", "*1111", "OK", -300.0, "RUB", "Lenta"])
    ws.append(["2026-01-06 10:00:00", "*1111", "OK", 95.78, "USD", "Interest"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_workbook_preview_splits_a_card_by_currency(client: TestClient) -> None:
    r = _upload(client, "/api/import/workbook/preview", _mixed_currency_book())
    assert r.status_code == 200, r.text
    assert r.json()["accountSlots"] == [
        {"key": "RUB:*1111", "marker": "*1111", "currency": "RUB", "transactions": 1},
        {"key": "USD:*1111", "marker": "*1111", "currency": "USD", "transactions": 1},
    ]


def test_workbook_commit_refuses_foreign_rows_on_a_ruble_account(
    api: Api,
    client: TestClient,
) -> None:
    rub = api.account("Card")
    data = _mixed_currency_book()
    mapping = json.dumps({"RUB:*1111": rub, "USD:*1111": rub})
    r = _upload(client, "/api/import/workbook/commit", data, {"mapping": mapping})
    assert r.status_code == 400
    assert "USD rows cannot be imported into a RUB account" in r.json()["detail"]

    usd = _required_id(
        client.post(
            "/api/accounts",
            json={
                "name": "Dollars",
                "type": "cash",
                "icon": "wallet",
                "color": "#5b6472",
                "currency": "USD",
                "openingBalance": 0,
                "bankRef": "",
            },
        ),
    )
    mapping = json.dumps({"RUB:*1111": rub, "USD:*1111": usd})
    r = _upload(client, "/api/import/workbook/commit", data, {"mapping": mapping})
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == 2


def _card_book() -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Transactions"
    ws.append(
        [
            "Operation date",
            "Card",
            "Status",
            "Operation amount",
            "Transaction currency",
            "Description",
        ],
    )
    ws.append(["2026-01-05 10:00:00", "*8181", "OK", -300.0, "RUB", "Lenta"])
    ws.append(["2026-01-06 10:00:00", "", "OK", -200.0, "RUB", "Okey"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_workbook_commit_remembers_card_markers_when_asked(api: Api, client: TestClient) -> None:
    """
    Mapping a card to an account is knowledge worth keeping: with remember set,.

    the marker's digits land in the account's card tails, so the next statement.
    import or sync routes that card without asking. The unmarked-rows slot has
    no digits and binds nothing.
    """
    acct = api.account("Card", cardTails=["1111"])
    other = api.account("Other")
    mapping = json.dumps({"RUB:*8181": acct, "RUB:": other})
    r = _upload(
        client,
        "/api/import/workbook/commit",
        _card_book(),
        {"mapping": mapping, "remember": "true"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["cardTailsBound"] == 1
    tails = {account.name: account.cardTails for account in api.snapshot().accounts}
    assert tails["Card"] == ["1111", "8181"]
    assert tails["Other"] == []


def test_workbook_commit_leaves_card_tails_alone_by_default(api: Api, client: TestClient) -> None:
    acct = api.account("Card")
    other = api.account("Other")
    mapping = json.dumps({"RUB:*8181": acct, "RUB:": other})
    r = _upload(client, "/api/import/workbook/commit", _card_book(), {"mapping": mapping})
    assert r.status_code == 200, r.text
    assert r.json()["cardTailsBound"] == 0
    assert all(account.cardTails == [] for account in api.snapshot().accounts)


def test_remembering_an_already_bound_marker_changes_nothing(api: Api, client: TestClient) -> None:
    acct = api.account("Card", cardTails=["8181"])
    other = api.account("Other")
    mapping = json.dumps({"RUB:*8181": acct, "RUB:": other})
    r = _upload(
        client,
        "/api/import/workbook/commit",
        _card_book(),
        {"mapping": mapping, "remember": "true"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["cardTailsBound"] == 0
    tails = {account.name: account.cardTails for account in api.snapshot().accounts}
    assert tails["Card"] == ["8181"]
