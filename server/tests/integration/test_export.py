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
    assert row[3] == round(125.5 / 5000.0, 2)
    assert row[4] == 4874.5
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=3)]
    header_idx = next(i for i, r in enumerate(rows) if r[0] == "Category")
    assert rows[header_idx][1] == 2026
    by_cat = {r[0]: r[1] for r in rows[header_idx + 1 :]}
    assert by_cat["Groceries"] == -125.5
    assert by_cat["Salary"] == 5000.0


def test_export_excludes_transfers_from_dashdata(api, client):
    _setup(api, client)
    a2 = api.account("Second")
    api.transfer(api.snapshot()["accounts"][0]["id"], a2, 10000, date="2026-01-15T12:00:00")
    ws = _export(client)["DashData"]
    row = [c.value for c in ws[2]]
    assert row[1] == 5000.0
    assert row[2] == 125.5


def test_export_transactions_static_columns(api, client):
    _setup(api, client)
    ws = _export(client)["Transactions"]
    row = [c.value for c in ws[2]]
    assert row[2] == "05.01.2026"
    assert row[3] is None or row[3] == ""
    assert row[6] == "RUB"
    assert row[8] == "RUB"
    assert row[9] is None or row[9] == ""
    assert ws.cell(row=2, column=6).number_format == "0.00"


def test_export_categories_layout(api, client):
    _setup(api, client)
    ws = _export(client)["Categories"]
    assert ws.freeze_panes == "A2"
    assert all(c.font.bold for c in ws[1])
    assert [c.value for c in ws[2]] == [1, "▼Daily Expenses", "Groceries", "lenta|okey"]
    assert [c.value for c in ws[3]] == [2, "▲Inflow", "Salary", None]
    assert ws.cell(row=4, column=1).value is None
    assert [c.value for c in ws[5]][:3] == ["Category Group", "Sort Order", "Type"]
    assert ws.cell(row=5, column=1).font.bold


def test_export_year_sheet_layout(api, client):
    _setup(api, client)
    ws = _export(client)["2026"]
    assert ws.freeze_panes == "B3"
    months = [ws.cell(row=1, column=2 + m * 3).value for m in range(12)]
    assert months == [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    merged = {str(r) for r in ws.merged_cells.ranges}
    assert "B1:D1" in merged
    assert "AI1:AK1" in merged
    assert [ws.cell(row=2, column=c).value for c in (35, 36, 37)] == [
        "Budgeted",
        "Outflows",
        "Balance",
    ]
    assert ws.cell(row=1, column=38).value == "Total"
    assert ws.cell(row=1, column=39).value == "Average"
    assert ws.column_dimensions["A"].width == 24
    assert ws.column_dimensions["B"].width == 11
    assert ws.cell(row=1, column=2).font.bold
    assert ws.cell(row=3, column=1).font.bold


def test_export_year_sheet_totals(api, client):
    _setup(api, client)
    ws = _export(client)["2026"]
    groceries_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Groceries"
    )
    assert ws.cell(row=groceries_row, column=38).value == 125.5
    assert ws.cell(row=groceries_row, column=39).value == 10.46
    assert ws.cell(row=groceries_row, column=5).value == 0.0
    assert ws.cell(row=groceries_row, column=6).value == 0.0
    assert ws.cell(row=groceries_row, column=7).value == 74.5
    assert ws.cell(row=3, column=38).value == 125.5
    assert ws.cell(row=3, column=39).value == 10.46
    salary_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Salary"
    )
    assert ws.cell(row=salary_row, column=3).value == 5000.0


def test_export_escapes_at_prefix(api, client):
    cat, acct = _setup(api, client)
    api.tx("2026-03-01T10:00:00", -100, accountId=acct, categoryId=cat, description="@cmd|test")
    ws = _export(client)["Transactions"]
    descriptions = {ws.cell(row=r, column=13).value for r in range(2, ws.max_row + 1)}
    assert "'@cmd|test" in descriptions


def test_export_dashdata_freeze_and_bold(api, client):
    _setup(api, client)
    ws = _export(client)["DashData"]
    assert ws.freeze_panes == "A2"
    assert all(c.font.bold for c in ws[1])


def test_export_amount_uses_account_currency_symbol(api, client):
    cat, _ = _setup(api, client)
    usd = api.account("Dollars", currency="USD")
    eur = api.account("Euros", currency="EUR")
    chf = api.account("Francs", currency="CHF")
    api.tx("2026-04-01T10:00:00", -30000, accountId=usd, categoryId=cat, description="Hotel")
    api.tx("2026-04-02T10:00:00", -20000, accountId=eur, categoryId=cat, description="Train")
    api.tx("2026-04-03T10:00:00", -10000, accountId=chf, categoryId=cat, description="Cheese")
    ws = _export(client)["Transactions"]
    amounts = {ws.cell(row=r, column=8).value for r in range(2, ws.max_row + 1)}
    assert "-125.50 ₽" in amounts
    assert "-300.00 $" in amounts
    assert "-200.00 €" in amounts
    assert "-100.00 CHF" in amounts


def test_export_dashdata_skips_uncategorized(api, client):
    _setup(api, client)
    api.tx("2026-01-25T10:00:00", -99900, description="Mystery")
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
    assert [c.value for c in wb["Categories"][1]] == [
        "Sort Order",
        "Category Group",
        "Category",
        "Keywords",
    ]
    assert wb["Transactions"].cell(row=1, column=1).value == "Дата операции"
    assert [c.value for c in wb["DashData"][1]] == ["Month", "Income", "Expense", "Ratio", "CumNet"]


def test_export_escapes_formula_prefixes(api, client):
    cat, acct = _setup(api, client)
    api.tx(
        "2026-02-01T10:00:00",
        -100,
        accountId=acct,
        categoryId=cat,
        description="=HYPERLINK(evil)",
        comment="+SUM(A1)",
    )
    ws = _export(client)["Transactions"]
    descriptions = {ws.cell(row=r, column=13).value for r in range(2, ws.max_row + 1)}
    comments = {ws.cell(row=r, column=16).value for r in range(2, ws.max_row + 1)}
    assert "'=HYPERLINK(evil)" in descriptions
    assert "'+SUM(A1)" in comments


def test_export_header_band_is_slate(api, client):
    _setup(api, client)
    wb = _export(client)
    for name in ("Categories", "Transactions", "DashData", "2026"):
        head = wb[name].cell(row=1, column=1)
        assert head.fill.fgColor.rgb == "FF3C464D"
        assert head.font.color.rgb == "FFFFFFFF"
        assert head.font.bold


def test_export_year_sheet_bands(api, client):
    _setup(api, client)
    ws = _export(client)["2026"]
    assert ws.cell(row=1, column=2).fill.fgColor.rgb == "FF3C464D"
    assert ws.cell(row=2, column=2).fill.fgColor.rgb == "FF3C464D"
    assert ws.cell(row=3, column=2).fill.fgColor.rgb == "FFEEF5E7"
    group_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "▼Daily Expenses"
    )
    assert ws.cell(row=group_row, column=1).fill.fgColor.rgb == "FFE6F4FB"


def test_export_summary_balance_is_colored(api, client):
    _setup(api, client)
    ws = _export(client)["2026"]
    balance = ws.cell(row=3, column=4)
    assert balance.value == 74.5
    assert balance.fill.fgColor.rgb == "FFEEF5E7"
    assert balance.font.color.rgb == "FF4F7A00"


def test_export_money_cells_have_grid_border(api, client):
    _setup(api, client)
    ws = _export(client)["2026"]
    groceries_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Groceries"
    )
    cell = ws.cell(row=groceries_row, column=2)
    assert cell.border.left.style == "thin"
    assert cell.border.bottom.style == "thin"


def test_export_positive_balance_is_green(api, client):
    _setup(api, client)
    ws = _export(client)["2026"]
    groceries_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Groceries"
    )
    balance = ws.cell(row=groceries_row, column=4)
    assert balance.value == 74.5
    assert balance.font.color.rgb == "FF4F7A00"


def test_export_negative_balance_is_red(api, client):
    g_out = api.group("Overspend")
    cat = api.category("Splurge", g_out)
    acct = api.account("Card")
    api.tx("2026-01-05T10:00:00", -20000, accountId=acct, categoryId=cat, description="Big")
    client.put("/api/budgets", json={"categoryId": cat, "year": 2026, "month": 1, "amount": 10000})
    ws = _export(client)["2026"]
    splurge_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Splurge"
    )
    balance = ws.cell(row=splurge_row, column=4)
    assert balance.value == -100.0
    assert balance.font.color.rgb == "FFC0392B"


def test_export_zero_balance_is_grey(api, client):
    g_out = api.group("OnBudget")
    cat = api.category("Exact", g_out)
    acct = api.account("Card")
    api.tx("2026-01-05T10:00:00", -10000, accountId=acct, categoryId=cat, description="Spend")
    client.put("/api/budgets", json={"categoryId": cat, "year": 2026, "month": 1, "amount": 10000})
    ws = _export(client)["2026"]
    exact_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Exact"
    )
    balance = ws.cell(row=exact_row, column=4)
    assert balance.value == 0.0
    assert balance.font.color.rgb == "FF434343"


def test_export_dashdata_refund_reduces_expense(api, client):
    cat, acct = _setup(api, client)
    api.tx("2026-01-20T10:00:00", 2550, accountId=acct, categoryId=cat, description="Refund")
    ws = _export(client)["DashData"]
    row = [c.value for c in ws[2]]
    assert row[1] == 5000.0
    assert row[2] == 100.0
