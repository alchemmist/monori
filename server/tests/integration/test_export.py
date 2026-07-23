from io import BytesIO

import pytest
from openpyxl import load_workbook

pytestmark = pytest.mark.integration

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _export(client):
    r = client.get("/api/export/xlsx")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(XLSX_MIME)
    assert "monori-export.xlsx" in r.headers["content-disposition"]
    return load_workbook(BytesIO(r.content))


def _setup(api, client):
    g_out = api.group("Daily Expenses")
    g_in = api.group("Inflow", kind="income")
    cat = api.category("Groceries", g_out, keywords="lenta|okey")
    salary = api.category("Salary", g_in)
    acct = api.account("Card")
    api.tx("2026-01-05T10:00:00", -12550, accountId=acct, categoryId=cat, description="Lenta")
    api.tx("2026-01-10T09:00:00", 500000, accountId=acct, categoryId=salary, description="Pay")
    client.put("/api/budgets", json={"categoryId": cat, "year": 2026, "month": 1, "amount": 20000})
    return cat, acct


def test_export_sheet_structure(api, client):
    _setup(api, client)
    wb = _export(client)
    assert wb.sheetnames == ["Categories", "Transactions", "2026", "DashData"]


def test_export_categories_sheet(api, client):
    _setup(api, client)
    ws = _export(client)["Categories"]
    assert [c.value for c in ws[1]] == ["Sort Order", "Category Group", "Category", "Keywords"]
    rows = [[c.value for c in row] for row in ws.iter_rows(min_row=2)]
    assert [1, "▼Daily Expenses", "Groceries", "lenta|okey"] in rows
    assert ["▼Daily Expenses", 1, "OUT"] in [r[:3] for r in rows]
    assert ["▲Inflow", 2, "IN"] in [r[:3] for r in rows]


def test_export_transactions_sheet(api, client):
    _setup(api, client)
    ws = _export(client)["Transactions"]
    headers = [c.value for c in ws[1]]
    assert headers[0] == "Дата операции"
    assert headers[-3:] == ["Monori Category", "Account", "Comment"]
    row = [c.value for c in ws[2]]
    assert row[0] == "05.01.2026 10:00:00"
    assert row[1] == "05.01.2026"
    assert row[4] == "OK"
    assert row[5] == -125.50
    assert row[7] == "-125.50 ₽"
    assert row[12] == "Lenta"
    assert row[13] == "Groceries"
    assert row[14] == "Card"


def test_export_year_sheet_grid(api, client):
    _setup(api, client)
    ws = _export(client)["2026"]
    assert ws.cell(row=1, column=2).value == "January"
    assert [ws.cell(row=2, column=c).value for c in (2, 3, 4)] == [
        "Budgeted",
        "Outflows",
        "Balance",
    ]
    labels = {ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)}
    assert "Month Summary" in labels
    assert "▼Daily Expenses" in labels
    assert "Groceries" in labels
    groceries_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Groceries"
    )
    assert ws.cell(row=groceries_row, column=2).value == 200.0
    assert ws.cell(row=groceries_row, column=3).value == 125.5
    assert ws.cell(row=groceries_row, column=4).value == 74.5
    assert ws.cell(row=3, column=2).value == 200.0
    assert ws.cell(row=3, column=3).value == 125.5


def test_export_dashdata_sheet(api, client):
    _setup(api, client)
    ws = _export(client)["DashData"]
    assert [c.value for c in ws[1]] == ["Month", "Income", "Expense", "Ratio", "CumNet"]
    row = [c.value for c in ws[2]]
    assert row[0] == "2026-01"
    assert row[1] == 5000.0
    assert row[2] == 125.5
    assert row[4] == 4874.5


def test_export_excludes_transfers_from_dashdata(api, client):
    _setup(api, client)
    a2 = api.account("Second")
    api.transfer(api.snapshot()["accounts"][0]["id"], a2, 10000, date="2026-01-15T12:00:00")
    ws = _export(client)["DashData"]
    row = [c.value for c in ws[2]]
    assert row[1] == 5000.0
    assert row[2] == 125.5


def test_export_requires_auth(anon):
    r = anon.get("/api/export/xlsx")
    assert r.status_code == 401


def test_export_empty_user(client):
    wb = _export(client)
    assert wb.sheetnames == ["Categories", "Transactions", "DashData"]
