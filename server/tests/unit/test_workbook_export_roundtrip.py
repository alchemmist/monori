import datetime
from io import BytesIO
from typing import TYPE_CHECKING, cast

import pytest
from openpyxl import Workbook

from app.workbook.parser import (
    WorkbookError,
    _amount,
    _parse_dt,
    _unquote,
    parse_workbook,
)

if TYPE_CHECKING:
    from openpyxl.worksheet.worksheet import Worksheet


def _book(
    categories: list[list[object]] | None = None,
    transactions: list[list[object]] | None = None,
    extra_sheets: dict[str, list[list[object]]] | None = None,
) -> bytes:
    wb = Workbook()
    ws = cast("Worksheet", wb.active)
    ws.title = "Categories"
    ws.append(["Sort Order", "Category Group", "Category", "Keywords"])
    for row in categories or []:
        ws.append(row)
    tx = wb.create_sheet("Transactions")
    tx.append(
        [
            "Дата операции",
            "Date",
            "Дата платежа",
            "Номер карты",
            "Status",
            "Сумма операции",
            "Валюта операции",
            "Amount",
            "Валюта платежа",
            "Кэшбэк",
            "Категория",
            "MCC",
            "Description",
            "Monori Category",
            "Account",
            "Comment",
        ]
    )
    for row in transactions or []:
        tx.append(row)
    for name, rows in (extra_sheets or {}).items():
        s = wb.create_sheet(name)
        for row in rows:
            s.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _year_header(months: int = 12) -> list[list[object]]:
    """The two header rows the exporter writes above a year grid."""
    names = [
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
    ][:months]
    top: list[object] = [None]
    sub: list[object] = [None]
    for name in names:
        top += [name, None, None]
        sub += ["Budgeted", "Outflows", "Balance"]
    return [top, sub]


def _tx_row(
    op: str = "05.01.2026 10:00:00",
    status: str = "OK",
    amount: object = -125.5,
    description: str = "Lenta",
    card: str = "",
    account: str = "",
    monori: str = "",
    comment: str = "",
) -> list[object]:
    return [
        op,
        "05.01.2026",
        "05.01.2026",
        card,
        status,
        amount,
        "RUB",
        "-125.50 ₽",
        "RUB",
        "",
        "Super",
        "5411",
        description,
        monori,
        account,
        comment,
    ]


def test_unquote_reverses_only_the_formula_escape() -> None:
    assert _unquote("'=SUM(A1)") == "=SUM(A1)"
    assert _unquote("'+A1") == "+A1"
    assert _unquote("'@cmd") == "@cmd"
    assert _unquote("plain") == "plain"
    assert _unquote("mid'dle") == "mid'dle"
    assert _unquote("'legit apostrophe") == "'legit apostrophe"


def test_parse_dt_variants() -> None:
    assert _parse_dt(datetime.datetime(2026, 1, 5, 10, 0)) == datetime.datetime(2026, 1, 5, 10, 0)
    assert _parse_dt(datetime.date(2026, 1, 5)) == datetime.datetime(2026, 1, 5)
    assert _parse_dt("05.01.2026 10:00:00") == datetime.datetime(2026, 1, 5, 10)
    assert _parse_dt("2026-01-05T10:00:00") == datetime.datetime(2026, 1, 5, 10)
    assert _parse_dt("") is None
    assert _parse_dt("garbage") is None
    assert _parse_dt(None) is None


def test_amount_variants() -> None:
    assert _amount(-125.5) == -12550
    assert _amount(500) == 50000
    assert _amount("-1 500,00") == -150000
    assert _amount("") is None
    assert _amount(None) is None
    assert _amount("abc") is None


def test_rejects_garbage_bytes() -> None:
    with pytest.raises(WorkbookError) as e:
        parse_workbook(b"nope")
    assert "not a readable .xlsx workbook" in str(e.value)


def test_transactions_are_the_only_required_sheet() -> None:
    """
    The category structure is read from a sheet of its own when there is one and
    inferred from the year grids when there isn't, so only the rows themselves
    are indispensable.
    """
    wb = Workbook()
    ws = cast("Worksheet", wb.active)
    ws.title = "Whatever"
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(WorkbookError) as e:
        parse_workbook(buf.getvalue())
    assert str(e.value) == "missing required sheet: Transactions"

    data = _book(transactions=[_tx_row(monori="Groceries")])
    parsed = parse_workbook(data)
    assert [t.monori_category for t in parsed.transactions] == ["Groceries"]


def test_missing_transactions_sheet() -> None:
    wb = Workbook()
    ws = cast("Worksheet", wb.active)
    ws.title = "Categories"
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(WorkbookError) as e:
        parse_workbook(buf.getvalue())
    assert str(e.value) == "missing required sheet: Transactions"


def test_missing_required_transaction_columns() -> None:
    wb = Workbook()
    ws = cast("Worksheet", wb.active)
    ws.title = "Categories"
    tx = wb.create_sheet("Transactions")
    tx.append(["Дата операции", "Status"])
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(WorkbookError) as e:
        parse_workbook(buf.getvalue())
    msg = str(e.value)
    assert msg.startswith("Transactions sheet is missing required columns:")
    assert "Сумма операции" in msg


def test_categories_main_and_group_tables() -> None:
    data = _book(
        categories=[
            [1, "▼Daily", "Groceries", "lenta|okey"],
            [2, "▲Inflow", "Salary", ""],
            [],
            ["Category Group", "Sort Order", "Type"],
            ["▼Daily", 1, "OUT"],
            ["▲Inflow", 2, "IN"],
        ]
    )
    parsed = parse_workbook(data)
    assert [(group.name, group.sort, group.kind) for group in parsed.groups] == [
        ("Daily", 1, "expense"),
        ("Inflow", 2, "income"),
    ]
    cats = {c.name: c for c in parsed.categories}
    assert cats["Groceries"].group == "Daily"
    assert cats["Groceries"].keywords == "lenta|okey"
    assert cats["Salary"].group == "Inflow"
    assert cats["Salary"].group_kind == "income"
    assert parsed.warnings == []


def test_categories_unrecognized_row_warns() -> None:
    data = _book(categories=[[1, "▼Daily", "Groceries", ""], ["junk", "row", None]])
    parsed = parse_workbook(data)
    assert any(w.startswith("Categories: unrecognized row skipped:") for w in parsed.warnings)


def test_category_sheet_saying_nothing_defers_to_the_grids() -> None:
    """
    The live spreadsheet has a sheet called Categories too, laid out nothing like
    ours. Rather than report every row of it, the reader treats a sheet it cannot
    read as absent and takes the structure from the year grids.
    """
    data = _book(categories=[["junk", "row", None], ["more", "junk", None]])
    parsed = parse_workbook(data)
    assert parsed.categories == []
    assert parsed.groups == []
    assert parsed.warnings == [
        "Categories: no category rows recognized (2 rows skipped),"
        " structure taken from the year grids"
    ]


def test_groups_derived_when_group_table_missing() -> None:
    data = _book(
        categories=[
            [3, "▼Daily", "Groceries", ""],
            [3, "▼Daily", "Cafes", ""],
            [5, "▲Inflow", "Salary", ""],
        ]
    )
    parsed = parse_workbook(data)
    assert "Categories: group table missing, groups derived from category rows" in parsed.warnings
    assert [(group.name, group.sort, group.kind) for group in parsed.groups] == [
        ("Daily", 3, "expense"),
        ("Inflow", 5, "income"),
    ]


def test_transactions_parse_and_markers() -> None:
    data = _book(
        transactions=[
            _tx_row(card="*2947", monori="Groceries", comment="note"),
            _tx_row(op="06.01.2026 09:30:00", amount="-1 500,00", account="Card", description="X"),
            _tx_row(status="FAILED"),
            [None] * 16,
        ]
    )
    parsed = parse_workbook(data)
    rows = parsed.transactions
    assert len(rows) == 2
    first, second = rows
    assert first.date == "2026-01-05T10:00:00"
    assert first.amount == -12550
    assert first.marker == "*2947"
    assert first.monori_category == "Groceries"
    assert first.comment == "note"
    assert first.bank_category == "Super"
    assert first.mcc == "5411"
    assert second.date == "2026-01-06T09:30:00"
    assert second.amount == -150000
    assert second.marker == "Card"
    assert parsed.warnings == ["Transactions: 1 non-OK rows skipped"]
    assert parsed.errors == []


def test_transactions_unparseable_rows_reported_with_row_number() -> None:
    data = _book(transactions=[_tx_row(op="garbage"), _tx_row(amount="zzz")])
    parsed = parse_workbook(data)
    assert parsed.transactions == []
    assert [(error.row, error.error) for error in parsed.errors] == [
        (2, "unparseable date or amount"),
        (3, "unparseable date or amount"),
    ]


def test_year_sheet_budgets_and_unknown_labels() -> None:
    year_rows: list[list[object]] = [
        ["Month Summary", 200, 125.5, 74.5],
        ["▼Daily", None, None, None],
        ["Groceries", 200, 125.5, 74.5, 300],
        ["Mystery", 1, 2, 3],
    ]
    data = _book(
        categories=[
            [1, "▼Daily", "Groceries", ""],
            ["Category Group", "Sort Order", "Type"],
            ["▼Daily", 1, "OUT"],
        ],
        extra_sheets={"2026": _year_header() + year_rows, "Notes": [["hi"]]},
    )
    parsed = parse_workbook(data)
    cells = parsed.budgets
    assert {(c.category, c.year, c.month, c.amount) for c in cells} == {
        ("Groceries", 2026, 1, 20000),
        ("Groceries", 2026, 2, 30000),
    }
    assert "2026: unknown row label skipped: Mystery" in parsed.warnings
    assert "unknown sheet ignored: Notes" in parsed.warnings


def test_year_sheet_only_four_digit_names() -> None:
    data = _book(extra_sheets={"20266": [["Groceries", 1]]})
    parsed = parse_workbook(data)
    assert parsed.budgets == []
    assert "unknown sheet ignored: 20266" in parsed.warnings


def test_dashdata_sheet_is_known_and_silent() -> None:
    data = _book(extra_sheets={"DashData": [["Month", "Income"]]})
    parsed = parse_workbook(data)
    assert parsed.warnings == []
