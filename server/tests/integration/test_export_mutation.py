"""
Export tests over a dataset with several transactions per category, more than
one month and a month without income. The single-row fixtures elsewhere cannot
tell an accumulation (`+=`) from an assignment (`=`), a three-wide month stride
from a four-wide one, or an empty ratio from a filled one — this one can.
"""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from tests.conftest import Api

pytestmark = pytest.mark.integration


def _export(client: TestClient) -> Workbook:
    r = client.get("/api/export/xlsx")
    assert r.status_code == 200, r.text
    return load_workbook(BytesIO(r.content))


def _rich(api: Api, client: TestClient) -> dict[str, int]:
    daily = api.group("Daily")
    inflow = api.group("Inflow", kind="income")
    groceries = api.category("Groceries", daily)
    cafes = api.category("Cafes", daily)
    salary = api.category("Salary", inflow)
    acct = api.account(
        "Card",
        type="card",
        icon="wallet",
        color="#5b6472",
        bankRef="card-1",
        currency="RUB",
        openingBalance=0,
    )
    # January: two grocery rows, one cafe row, two salary rows
    api.tx("2026-01-05T10:00:00", -10000, accountId=acct, categoryId=groceries, description="G1")
    api.tx("2026-01-06T10:00:00", -5000, accountId=acct, categoryId=groceries, description="G2")
    api.tx("2026-01-07T10:00:00", -3000, accountId=acct, categoryId=cafes, description="C1")
    api.tx("2026-01-10T10:00:00", 500000, accountId=acct, categoryId=salary, description="S1")
    api.tx("2026-01-11T10:00:00", 100000, accountId=acct, categoryId=salary, description="S2")
    # February: one grocery row, no income
    api.tx("2026-02-05T10:00:00", -20000, accountId=acct, categoryId=groceries, description="G3")
    # March: expense only, so its income is zero and the ratio is blank
    api.tx("2026-03-05T10:00:00", -4000, accountId=acct, categoryId=cafes, description="C2")
    for month, cat, amount in (
        (1, groceries, 30000),
        (1, cafes, 20000),
        (2, groceries, 40000),
    ):
        client.put(
            "/api/budgets",
            json={"categoryId": cat, "year": 2026, "month": month, "amount": amount},
        )
    return {"groceries": groceries, "cafes": cafes, "salary": salary, "acct": acct}


def _row_of(ws: Worksheet, label: str) -> int:
    return next(r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == label)


def test_year_sheet_sums_repeated_category_rows(api: Api, client: TestClient) -> None:
    _rich(api, client)
    ws = _export(client)["2026"]
    row = _row_of(ws, "Groceries")
    # two January grocery rows: -100 and -50 -> the month's outflow is 150, not 50
    assert ws.cell(row=row, column=3).value == 150.0


def test_month_summary_sums_across_categories(api: Api, client: TestClient) -> None:
    _rich(api, client)
    ws = _export(client)["2026"]
    # Month Summary budgeted for January is Groceries 300 + Cafes 200
    assert ws.cell(row=3, column=2).value == 500.0


def test_year_sheet_uses_a_three_wide_month_stride(api: Api, client: TestClient) -> None:
    _rich(api, client)
    ws = _export(client)["2026"]
    row = _row_of(ws, "Groceries")
    # February's block starts at column 2 + (2-1)*3 = 5
    assert ws.cell(row=row, column=5).value == 400.0
    assert ws.cell(row=row, column=6).value == 200.0


def test_year_sheet_money_cells_keep_the_number_font(api: Api, client: TestClient) -> None:
    _rich(api, client)
    ws = _export(client)["2026"]
    row = _row_of(ws, "Groceries")
    assert ws.cell(row=row, column=2).font.color.rgb == "FF434343"


def _dash_row(ws: Worksheet, month: str) -> list[object]:
    idx = next(r for r in range(2, ws.max_row + 1) if ws.cell(row=r, column=1).value == month)
    return [ws.cell(row=idx, column=c).value for c in range(1, 6)]


def test_dashdata_sums_income_across_rows(api: Api, client: TestClient) -> None:
    _rich(api, client)
    ws = _export(client)["DashData"]
    jan = _dash_row(ws, "2026-01")
    # two salary rows, 5000 + 1000
    assert jan[1] == 6000.0


def test_dashdata_carries_a_running_cumulative_net(api: Api, client: TestClient) -> None:
    _rich(api, client)
    ws = _export(client)["DashData"]
    # Jan net = 6000 - (150 + 30) = 5820; Feb net = 0 - 200; cumulative = 5620
    assert _dash_row(ws, "2026-01")[4] == 5820.0
    assert _dash_row(ws, "2026-02")[4] == 5620.0


def test_dashdata_leaves_the_ratio_blank_without_income(api: Api, client: TestClient) -> None:
    _rich(api, client)
    ws = _export(client)["DashData"]
    march = _dash_row(ws, "2026-03")
    assert march[2] == 40.0  # expense present
    assert march[3] is None  # income zero -> ratio blank -> empty cell reads back as None


def test_transactions_sheet_is_frozen_below_the_header(api: Api, client: TestClient) -> None:
    _rich(api, client)
    ws = _export(client)["Transactions"]
    assert ws.freeze_panes == "A2"
