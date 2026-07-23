"""Builds the YNAB-style export workbook from a snapshot dict.

The workbook layout (sheet names, glyphs, column orders) is defined in
``spec.py`` and shared with the future spreadsheet importer so the two
directions never drift.
"""

import datetime
from collections import defaultdict
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from . import spec

BOLD = Font(bold=True)
CENTER = Alignment(horizontal="center")


def _parse_dt(value: str) -> datetime.datetime:
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return datetime.datetime.fromisoformat(value[:10])


def _money_cell(ws, row: int, col: int, kop: int):
    cell = ws.cell(row=row, column=col, value=spec.kop_to_rub(kop))
    cell.number_format = spec.MONEY_FORMAT
    return cell


def _categories_sheet(ws, snap):
    ws.title = spec.SHEET_CATEGORIES
    ws.append(spec.CATEGORY_HEADERS)
    for cell in ws[1]:
        cell.font = BOLD
    by_group = defaultdict(list)
    for cat in snap["categories"]:
        by_group[cat["groupId"]].append(cat)
    for group in snap["groups"]:
        display = spec.group_display(group["name"], group["kind"])
        for cat in by_group[group["id"]]:
            ws.append([group["sort"], display, cat["name"], cat["keywords"]])
    ws.append([])
    header_row = ws.max_row + 1
    ws.append(spec.GROUP_HEADERS)
    for cell in ws[header_row]:
        cell.font = BOLD
    for group in snap["groups"]:
        ws.append(
            [
                spec.group_display(group["name"], group["kind"]),
                group["sort"],
                spec.group_type(group["kind"]),
            ]
        )
    ws.freeze_panes = "A2"


def _transactions_sheet(ws, snap, cat_names, acct_names, acct_currency):
    ws.append(spec.TRANSACTION_HEADERS)
    for cell in ws[1]:
        cell.font = BOLD
    row = 2
    for tx in snap["transactions"]:
        dt = _parse_dt(tx["date"])
        currency = acct_currency.get(tx["accountId"], "RUB")
        rub = spec.kop_to_rub(tx["amount"])
        ws.cell(row=row, column=1, value=dt.strftime("%d.%m.%Y %H:%M:%S"))
        ws.cell(row=row, column=2, value=dt.strftime("%d.%m.%Y"))
        ws.cell(row=row, column=3, value=dt.strftime("%d.%m.%Y"))
        ws.cell(row=row, column=4, value="")
        ws.cell(row=row, column=5, value="OK")
        _money_cell(ws, row, 6, tx["amount"])
        ws.cell(row=row, column=7, value=currency)
        ws.cell(row=row, column=8, value=f"{rub:.2f} ₽")
        ws.cell(row=row, column=9, value=currency)
        ws.cell(row=row, column=10, value="")
        ws.cell(row=row, column=11, value=tx["bankCategory"])
        ws.cell(row=row, column=12, value=tx["mcc"])
        ws.cell(row=row, column=13, value=tx["description"])
        ws.cell(row=row, column=14, value=cat_names.get(tx["categoryId"], ""))
        ws.cell(row=row, column=15, value=acct_names.get(tx["accountId"], ""))
        ws.cell(row=row, column=16, value=tx["comment"])
        row += 1
    ws.freeze_panes = "A2"


def _month_activity(snap):
    activity: defaultdict[tuple[int, int, int], int] = defaultdict(int)
    for tx in snap["transactions"]:
        if tx["categoryId"] is None:
            continue
        dt = _parse_dt(tx["date"])
        activity[(tx["categoryId"], dt.year, dt.month)] += tx["amount"]
    return activity


def _budget_index(snap):
    budgets = {}
    for cell in snap["budgets"]:
        budgets[(cell["categoryId"], cell["year"], cell["month"])] = cell["amount"]
    return budgets


def _year_sheet(ws, year, snap, activity, budgets):
    for m in range(12):
        col = 2 + m * 3
        head = ws.cell(row=1, column=col, value=spec.MONTHS[m])
        head.font = BOLD
        head.alignment = CENTER
        ws.merge_cells(
            start_row=1, start_column=col, end_row=1, end_column=col + 2
        )
        for i, label in enumerate(spec.MONTH_COLS):
            ws.cell(row=2, column=col + i, value=label).font = BOLD
    total_col = 2 + 12 * 3
    ws.cell(row=1, column=total_col, value="Total").font = BOLD
    ws.cell(row=1, column=total_col + 1, value="Average").font = BOLD

    by_group = defaultdict(list)
    for cat in snap["categories"]:
        by_group[cat["groupId"]].append(cat)

    hero = {m: [0, 0, 0] for m in range(1, 13)}
    row = 4
    for group in snap["groups"]:
        cats = by_group[group["id"]]
        if not cats:
            continue
        label = ws.cell(
            row=row, column=1, value=spec.group_display(group["name"], group["kind"])
        )
        label.font = BOLD
        row += 1
        expense = group["kind"] == "expense"
        for cat in cats:
            ws.cell(row=row, column=1, value=cat["name"])
            balance = 0
            total_out = 0
            for m in range(1, 13):
                budgeted = budgets.get((cat["id"], year, m), 0)
                signed = activity.get((cat["id"], year, m), 0)
                out = -signed if expense else signed
                balance += budgeted - out
                col = 2 + (m - 1) * 3
                _money_cell(ws, row, col, budgeted)
                _money_cell(ws, row, col + 1, out)
                _money_cell(ws, row, col + 2, balance)
                total_out += out
                if expense:
                    hero[m][0] += budgeted
                    hero[m][1] += out
            _money_cell(ws, row, total_col, total_out)
            _money_cell(ws, row, total_col + 1, round(total_out / 12))
            row += 1
        row += 1

    hero_balance = 0
    ws.cell(row=3, column=1, value="Month Summary").font = BOLD
    hero_total = 0
    for m in range(1, 13):
        budgeted, out, _ = hero[m]
        hero_balance += budgeted - out
        col = 2 + (m - 1) * 3
        _money_cell(ws, 3, col, budgeted)
        _money_cell(ws, 3, col + 1, out)
        _money_cell(ws, 3, col + 2, hero_balance)
        hero_total += out
    _money_cell(ws, 3, total_col, hero_total)
    _money_cell(ws, 3, total_col + 1, round(hero_total / 12))
    for cell in ws[3]:
        cell.font = BOLD

    ws.freeze_panes = "B3"
    ws.column_dimensions["A"].width = 24
    for c in range(2, total_col + 2):
        ws.column_dimensions[get_column_letter(c)].width = 11


def _dashdata_sheet(ws, snap, activity):
    ws.append(spec.DASH_HEADERS)
    for cell in ws[1]:
        cell.font = BOLD
    monthly: defaultdict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
    for tx in snap["transactions"]:
        if tx["transferId"]:
            continue
        dt = _parse_dt(tx["date"])
        key = (dt.year, dt.month)
        if tx["amount"] > 0:
            monthly[key][0] += tx["amount"]
        else:
            monthly[key][1] -= tx["amount"]
    cum_net = 0
    row = 2
    for year, month in sorted(monthly):
        income, expense = monthly[(year, month)]
        cum_net += income - expense
        ws.cell(row=row, column=1, value=f"{year:04d}-{month:02d}")
        _money_cell(ws, row, 2, income)
        _money_cell(ws, row, 3, expense)
        ratio = round(expense / income, 2) if income else ""
        ws.cell(row=row, column=4, value=ratio)
        _money_cell(ws, row, 5, cum_net)
        row += 1

    years = sorted({y for (_, y, _m) in activity})
    if years:
        row += 1
        ws.cell(row=row, column=1, value="Category").font = BOLD
        for i, year in enumerate(years):
            ws.cell(row=row, column=2 + i, value=year).font = BOLD
        for cat in snap["categories"]:
            row += 1
            ws.cell(row=row, column=1, value=cat["name"])
            for i, year in enumerate(years):
                total = sum(
                    activity.get((cat["id"], year, m), 0) for m in range(1, 13)
                )
                _money_cell(ws, row, 2 + i, total)
    ws.freeze_panes = "A2"


def build_workbook(snap) -> Workbook:
    cat_names = {c["id"]: c["name"] for c in snap["categories"]}
    acct_names = {a["id"]: a["name"] for a in snap["accounts"]}
    acct_currency = {a["id"]: a["currency"] for a in snap["accounts"]}
    activity = _month_activity(snap)
    budgets = _budget_index(snap)

    wb = Workbook()
    _categories_sheet(wb.active, snap)
    _transactions_sheet(
        wb.create_sheet(spec.SHEET_TRANSACTIONS), snap, cat_names, acct_names, acct_currency
    )
    years = sorted(
        {y for (_, y, _m) in activity} | {b["year"] for b in snap["budgets"]}
    )
    for year in years:
        _year_sheet(wb.create_sheet(str(year)), year, snap, activity, budgets)
    _dashdata_sheet(wb.create_sheet(spec.SHEET_DASHDATA), snap, activity)
    return wb


def workbook_bytes(snap) -> bytes:
    buf = BytesIO()
    build_workbook(snap).save(buf)
    return buf.getvalue()
