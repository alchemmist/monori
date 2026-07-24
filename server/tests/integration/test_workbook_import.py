import json

import pytest
from conftest import login_as

pytestmark = pytest.mark.integration


def _seed(api, client):
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


def _export_bytes(client):
    r = client.get("/api/export/xlsx")
    assert r.status_code == 200
    return r.content


def _upload(client, path, data, extra=None):
    files = {"file": ("book.xlsx", data, "application/octet-stream")}
    return client.post(path, files=files, data=extra or {})


def test_workbook_preview_summarizes(api, client):
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
    assert body["accountMarkers"] == ["Card"]
    assert body["errors"] == []


def test_workbook_preview_rejects_garbage(client):
    r = _upload(client, "/api/import/workbook/preview", b"not an xlsx")
    assert r.status_code == 400
    assert "workbook" in r.json()["detail"]


def test_workbook_commit_requires_full_mapping(api, client):
    _seed(api, client)
    data = _export_bytes(client)
    r = _upload(client, "/api/import/workbook/commit", data, {"mapping": "{}"})
    assert r.status_code == 400
    assert "unmapped" in r.json()["detail"]


def test_workbook_commit_rejects_foreign_account(api, client):
    _seed(api, client)
    data = _export_bytes(client)
    other = login_as(client, "other@example.com")
    r = client.post(
        "/api/import/workbook/commit",
        files={"file": ("book.xlsx", data, "application/octet-stream")},
        data={"mapping": json.dumps({"Card": 1})},
        headers=other,
    )
    assert r.status_code == 400


def test_workbook_roundtrip_into_fresh_user(api, client):
    _seed(api, client)
    data = _export_bytes(client)

    client.headers.update(login_as(client, "fresh@example.com"))
    r = client.post("/api/accounts", json={"name": "Imported card"})
    assert r.status_code == 200
    target = r.json()["id"]

    r = client.post(
        "/api/import/workbook/commit",
        files={"file": ("book.xlsx", data, "application/octet-stream")},
        data={"mapping": json.dumps({"Card": target})},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["groupsCreated"] == 2
    assert result["categoriesCreated"] == 2
    assert result["inserted"] == 3
    assert result["skipped"] == 0
    assert result["budgetsWritten"] == 2

    snap = client.get("/api/snapshot").json()
    assert {g["name"] for g in snap["groups"]} >= {"Daily Expenses", "Inflow"}
    kinds = {g["name"]: g["kind"] for g in snap["groups"]}
    assert kinds["Inflow"] == "income"
    assert kinds["Daily Expenses"] == "expense"
    cats = {c["name"]: c for c in snap["categories"]}
    assert cats["Groceries"]["keywords"] == "lenta|okey"
    txs = sorted(snap["transactions"], key=lambda t: t["date"])
    assert [(t["date"], t["amount"], t["description"]) for t in txs] == [
        ("2026-01-05T10:00:00", -12550, "Lenta"),
        ("2026-01-10T09:00:00", 500000, "Pay"),
        ("2026-02-01T12:00:00", -700, "Okey market"),
    ]
    assert txs[0]["categoryId"] == cats["Groceries"]["id"]
    assert txs[1]["categoryId"] == cats["Salary"]["id"]
    assert txs[2]["categoryId"] == cats["Groceries"]["id"]
    budgets = {(b["month"]): b["amount"] for b in snap["budgets"]}
    assert budgets == {1: 20000, 2: 30000}


def test_workbook_reimport_is_idempotent(api, client):
    _seed(api, client)
    data = _export_bytes(client)
    client.headers.update(login_as(client, "again@example.com"))
    target = client.post("/api/accounts", json={"name": "T"}).json()["id"]
    payload = {"mapping": json.dumps({"Card": target})}
    files = {"file": ("book.xlsx", data, "application/octet-stream")}
    first = client.post("/api/import/workbook/commit", files=files, data=payload).json()
    second = client.post("/api/import/workbook/commit", files=files, data=payload).json()
    assert first["inserted"] == 3
    assert second["inserted"] == 0
    assert second["skipped"] == 3
    assert second["groupsCreated"] == 0
    assert second["categoriesCreated"] == 0
    snap = client.get("/api/snapshot").json()
    assert len(snap["transactions"]) == 3


def test_workbook_budget_policy_skip(api, client):
    _seed(api, client)
    data = _export_bytes(client)
    client.headers.update(login_as(client, "policy@example.com"))
    target = client.post("/api/accounts", json={"name": "T"}).json()["id"]
    files = {"file": ("book.xlsx", data, "application/octet-stream")}
    r = client.post(
        "/api/import/workbook/commit",
        files=files,
        data={"mapping": json.dumps({"Card": target})},
    )
    assert r.status_code == 200
    snap = client.get("/api/snapshot").json()
    groceries = next(c for c in snap["categories"] if c["name"] == "Groceries")
    client.put(
        "/api/budgets",
        json={"categoryId": groceries["id"], "year": 2026, "month": 1, "amount": 777},
    )
    r = client.post(
        "/api/import/workbook/commit",
        files=files,
        data={"mapping": json.dumps({"Card": target}), "budgetPolicy": "skip"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["budgetsSkipped"] == 2
    assert body["budgetsWritten"] == 0
    snap = client.get("/api/snapshot").json()
    jan = next(b for b in snap["budgets"] if b["month"] == 1)
    assert jan["amount"] == 777
    r = client.post(
        "/api/import/workbook/commit",
        files=files,
        data={"mapping": json.dumps({"Card": target}), "budgetPolicy": "overwrite"},
    )
    assert r.json()["budgetsWritten"] == 2
    snap = client.get("/api/snapshot").json()
    jan = next(b for b in snap["budgets"] if b["month"] == 1)
    assert jan["amount"] == 20000


def test_workbook_commit_bad_policy_and_mapping(api, client):
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


def test_workbook_import_lands_as_rollbackable_batch(api, client):
    _seed(api, client)
    data = _export_bytes(client)
    client.headers.update(login_as(client, "batch@example.com"))
    target = client.post("/api/accounts", json={"name": "T"}).json()["id"]
    r = client.post(
        "/api/import/workbook/commit",
        files={"file": ("book.xlsx", data, "application/octet-stream")},
        data={"mapping": json.dumps({"Card": target})},
    )
    batch = r.json()["batches"][0]
    assert batch["accountId"] == target
    assert batch["inserted"] == 3


def test_workbook_upload_guards(api, client, monkeypatch):
    r = client.post(
        "/api/import/workbook/preview",
        files={"file": ("book.xlsx", b"", "application/octet-stream")},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "empty upload"

    import app.routers.imports as imports_mod

    monkeypatch.setattr(imports_mod, "WORKBOOK_MAX_BYTES", 10)
    r = client.post(
        "/api/import/workbook/preview",
        files={"file": ("book.xlsx", b"x" * 11, "application/octet-stream")},
    )
    assert r.status_code == 413
    assert r.json()["detail"] == "workbook is too large"
