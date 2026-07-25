"""
Reads a budget workbook — ours or the live "Budget YNAB-Like" Google-Sheets
spreadsheet monori grew from — into {groups, categories, transactions, budgets}.

There is one pipeline, not one per file we have seen. What a workbook happens to
carry is read off its own content: which columns the transaction sheet names,
whether the category structure is spelled out on a sheet of its own or only
implied by the sections of the year grids, and whether a month has rows in it or
just the totals the sheet cached. So a workbook is never classified; it is
measured, and every stage does the most it can with what is actually there.

The last part matters most. A hand-kept spreadsheet holds real rows only for
recent months and keeps its earlier history as cached aggregates. Those months
are rebuilt from the aggregates with synthetic "Migration" transactions so the
budgeted / outflows / balance / available figures survive the move. A month that
does carry rows is never touched: the rows are the truth, and a total that
disagrees with them is reported, never reconciled away.
"""

import datetime
import re
from io import BytesIO

from openpyxl import load_workbook

from ..importer import parse_amount_kop, parse_date
from . import spec

YEAR_RE = re.compile(r"^(\d{4})(_archive)?$")

# Every name a transaction column is known to go by. A workbook exported by
# monori writes the English ones, the live spreadsheet the Russian ones, and
# both are just names for the same field — so the reader resolves columns by
# meaning and never has to know which kind of file it was handed.
TX_ALIASES = {
    "date": ("Дата операции", "Date"),
    "card": ("Номер карты",),
    "account": ("Account",),
    "status": ("Статус", "Status"),
    "amount": ("Сумма операции", "Amount"),
    "currency": ("Валюта операции",),
    "pay_amount": ("Сумма платежа",),
    "pay_currency": ("Валюта платежа",),
    "bank_category": ("Категория",),
    "mcc": ("MCC",),
    "description": ("Описание", "Description"),
    "category": ("Monori Category",),
    "comment": ("Comment",),
}

# a row is only worth reading if it can say when it happened and for how much
TX_REQUIRED = ("date", "amount")

MONTH_ABBREVS = {
    "ЯНВ": 1,
    "ФЕВ": 2,
    "МАР": 3,
    "АПР": 4,
    "МАЙ": 5,
    "МАЯ": 5,
    "ИЮН": 6,
    "ИЮЛ": 7,
    "АВГ": 8,
    "СЕН": 9,
    "ОКТ": 10,
    "НОЯ": 11,
    "ДЕК": 12,
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

# every header a workbook is known to name on the transaction sheet; anything
# to the right of the last of these is the sheet's own bookkeeping (an unnamed
# category column, the keyword side table) rather than data with a header
KNOWN_TX_HEADERS = tuple(name for names in TX_ALIASES.values() for name in names) + (
    "Дата платежа",
    "Кэшбэк",
    "Бонусы (включая кэшбэк)",
    "Округление на инвесткопилку",
    "Сумма операции с округлением",
)

# the keyword table and category column live in the first few hundred rows;
# scanning the whole multi-thousand-row transaction log for them is wasted work
SIDE_TABLE_SCAN_ROWS = 500

BUDGET_HEADERS = ("Бюджет", "Budgeted")
OUTFLOW_HEADERS = ("Расход", "Outflows")
BALANCE_HEADERS = ("Баланс", "Balance")
LABEL_HEADERS = ("Категория", "Категории", "Category", "Categories")
SKIP_LABELS = LABEL_HEADERS + ("Month Summary", "Total", "Итого")

DEFAULT_CURRENCY = "RUB"
INCOME_GROUP = "Inflow"
INCOME_CATEGORY = "Income"
OTHER_GROUP = "Other"

ADJUST_TOLERANCE_KOP = 2
VERIFY_TOLERANCE_KOP = 5


class WorkbookError(Exception):
    pass


def _s(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


SUM_FORMULA_RE = re.compile(r"^=[-+]?\d+(\.\d+)?([-+]\d+(\.\d+)?)*$")


def _kop(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        cleaned = re.sub(r"[\s\u00a0\u202f]", "", value).replace(",", ".")
        if not cleaned:
            return None
        # a split the user typed straight into the cell (`=-48480+16990`); the
        # workbook may carry no cached result for it, so add the terms up here
        # rather than lose the row
        if SUM_FORMULA_RE.match(cleaned):
            terms = re.findall(r"[-+]?\d+(?:\.\d+)?", cleaned[1:])
            return spec.kop_from_rub(sum(float(t) for t in terms))
        try:
            value = float(cleaned)
        except ValueError:
            return None
    if not isinstance(value, int | float):
        return None
    return spec.kop_from_rub(value)


def _last_day(year, month):
    end = datetime.date(year + 1, 1, 1) if month == 12 else datetime.date(year, month + 1, 1)
    return end - datetime.timedelta(days=1)


def _stamp(year, month):
    return _last_day(year, month).strftime("%Y-%m-%dT12:00:00")


def _month_num(value):
    abbr = _s(value).upper()[:3]
    return MONTH_ABBREVS.get(abbr)


def _find_layout(ws):
    """
    Locates the month blocks of a year sheet by looking for the row that repeats
    a Budgeted/Outflows/Balance header per month — which is the same grid in a
    workbook we wrote and in the hand-kept spreadsheet, only sitting at a
    different row and labelled in a different language. Returns None when no
    such row exists, which is how a sheet says it is not a year grid at all.
    """
    for r in range(1, 11):
        row = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        bases = [i + 1 for i, v in enumerate(row) if _s(v) in BUDGET_HEADERS]
        if len(bases) < 2:
            continue
        out_off = bal_off = None
        for i, v in enumerate(row):
            col = i + 1
            if col <= bases[0]:
                continue
            if _s(v) in OUTFLOW_HEADERS and out_off is None:
                out_off = col - bases[0]
            if _s(v) in BALANCE_HEADERS and bal_off is None:
                bal_off = col - bases[0]
        if out_off is None or bal_off is None:
            continue
        label_col = None
        for rr in (r, r + 1):
            for c in range(1, bases[0]):
                if _s(ws.cell(rr, c).value) in LABEL_HEADERS:
                    label_col = c
                    break
            if label_col:
                break
        start_month = None
        for rr in (1, 2, 3):
            mon = _month_num(ws.cell(rr, bases[0]).value)
            if mon:
                start_month = mon
                break
        return {
            "header_row": r,
            "bases": bases,
            "out_off": out_off,
            "bal_off": bal_off,
            "label_col": label_col or _label_col(ws, r, bases[0]),
            "start_month": start_month or 1,
        }
    return None


def _label_col(ws, header_row, first_base):
    """
    The category column when the grid never names it: of the columns left of the
    first month block, the one carrying the most labels below the header.
    """
    best, best_count = 1, 0
    for c in range(1, first_base):
        count = sum(
            1
            for r in range(header_row + 1, min(ws.max_row, header_row + 60) + 1)
            if _s(ws.cell(r, c).value)
        )
        if count > best_count:
            best, best_count = c, count
    return best


def _kind_of(group_name, groups):
    return next((g["kind"] for g in groups if g["name"] == group_name), "expense")


def _parse_categories(ws, warnings):
    """
    Reads a category sheet that states the structure outright: category rows
    (`sort | group | category | keywords`) and, when present, a group table
    (`group | sort | IN/OUT`). Groups fall back to the ones the category rows
    name so a sheet missing that table still imports.
    """
    groups = []
    categories = []
    group_rows_seen = False
    for row in ws.iter_rows(min_row=1, values_only=True):
        cells = list(row) + [None] * (4 - len(row))
        c1, c2, c3, c4 = cells[:4]
        s1, s2, s3 = _s(c1), _s(c2), _s(c3)
        if s1 in ("Sort Order", "Category Group") or (not s1 and not s2):
            continue
        if s3 in (spec.TYPE_IN, spec.TYPE_OUT) and isinstance(c2, int | float):
            name, _ = spec.strip_glyph(_unquote(s1))
            groups.append(
                {
                    "name": name,
                    "sort": int(c2),
                    "kind": "income" if s3 == spec.TYPE_IN else "expense",
                }
            )
            group_rows_seen = True
            continue
        if isinstance(c1, int | float) and s2 and s3:
            name, kind = spec.strip_glyph(_unquote(s2))
            categories.append(
                {
                    "group": name,
                    "group_kind": kind,
                    "group_sort": int(c1),
                    "name": _unquote(s3),
                    "keywords": _unquote(_s(c4)),
                }
            )
            continue
        if s1 or s2 or s3:
            warnings.append(f"Categories: unrecognized row skipped: {[s1, s2, s3][:3]}")
    if not group_rows_seen:
        seen: dict[str, dict] = {}
        for cat in categories:
            if str(cat["group"]) not in seen:
                seen[str(cat["group"])] = {
                    "name": cat["group"],
                    "sort": cat["group_sort"],
                    "kind": cat["group_kind"] or "expense",
                }
        groups = list(seen.values())
        if groups:
            warnings.append("Categories: group table missing, groups derived from category rows")
    return groups, categories


def _sheet_sections(ws, layout):
    """
    Splits the category area into (group, [(row, category), ...]) sections.
    A row whose label starts with a kind glyph opens a group; in the old
    glyph-less layout the first labelled row after a fully blank gap does.
    """
    label_col = layout["label_col"]
    sections: list[dict] = []
    current: dict | None = None
    in_gap = True
    for r in range(layout["header_row"] + 1, ws.max_row + 1):
        label = _s(ws.cell(r, label_col).value)
        if not label or label in SKIP_LABELS:
            in_gap = in_gap or not label
            if label in SKIP_LABELS:
                in_gap = True
            continue
        name, kind = spec.strip_glyph(label)
        if kind is not None or (in_gap and current is None) or (in_gap and current is not None):
            current = {"name": name, "kind": kind or "expense", "rows": []}
            sections.append(current)
        elif current is None:
            current = {"name": name, "kind": "expense", "rows": []}
            sections.append(current)
        else:
            current["rows"].append((r, label))
        in_gap = False
    return sections


def _summary_value(ws, base, labels):
    for r in range(1, 7):
        text = _s(ws.cell(r, base + 2).value)
        if any(text.startswith(lb) for lb in labels):
            return _kop(ws.cell(r, base + 1).value)
    return None


def _parse_year_sheet(ws, year, layout):
    months = []
    for i, base in enumerate(layout["bases"]):
        m = layout["start_month"] + i
        if m > 12:
            break
        months.append((m, base))
    cats: dict[str, dict] = {}
    for section in _sheet_sections(ws, layout):
        for r, name in section["rows"]:
            entry = cats.setdefault(
                name,
                {"group": section["name"], "budgets": {}, "outflows": {}, "balances": {}},
            )
            for m, base in months:
                b = _kop(ws.cell(r, base).value)
                o = _kop(ws.cell(r, base + layout["out_off"]).value)
                bal = _kop(ws.cell(r, base + layout["bal_off"]).value)
                if b is not None:
                    entry["budgets"][m] = b
                if o is not None:
                    entry["outflows"][m] = o
                if bal is not None:
                    entry["balances"][m] = bal
    income = {}
    available = {}
    for m, base in months:
        inc = _summary_value(ws, base, ("Income for", "Поступления в"))
        if inc is not None:
            income[m] = inc
        for r in (5, 6):
            label = _s(ws.cell(r + 1, base + 1).value)
            if label.startswith(("Available", "Доступный")):
                av = _kop(ws.cell(r, base + 1).value)
                if av is not None:
                    available[m] = av
                break
    seed = None
    first_base = months[0][1] if months else None
    if first_base is not None:
        label = _s(ws.cell(1, first_base + 2).value)
        if label.startswith(("Not budgeted", "Не заложено")):
            seed = _kop(ws.cell(1, first_base + 1).value)
    return {
        "year": year,
        "months": [m for m, _ in months],
        "cats": cats,
        "income": income,
        "available": available,
        "seed": seed,
        "sections": _sheet_sections(ws, layout),
    }


def _tx_header_index(ws):
    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if header is None:
        return None
    return {_s(v): i for i, v in enumerate(header) if _s(v)}


def _parse_dt(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    text = _s(value)
    if not text:
        return None
    parsed = parse_date(text)
    if parsed:
        return parsed
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def _unquote(value: str) -> str:
    """
    Reverses our exporter's formula-escape and nothing else: a leading
    apostrophe is stripped only when it guards a formula prefix, so a value that
    legitimately starts with one survives the round-trip.
    """
    if value.startswith("'") and value[1:].startswith(("=", "+", "@")):
        return value[1:]
    return value


def _amount(value):
    """Kopecks from a cell that may be a number, a formatted string, or blank."""
    kop = _kop(value)
    if kop is not None:
        return kop
    text = _s(value)
    return parse_amount_kop(text) if text else None


def _tx_columns(idx):
    """Which column, if any, holds each field this reader knows how to use."""
    return {
        field: next((idx[name] for name in names if name in idx), None)
        for field, names in TX_ALIASES.items()
    }


def _parse_transactions(ws, warnings, errors):
    idx = _tx_header_index(ws)
    if idx is None:
        raise WorkbookError("Transactions sheet is empty")
    at = _tx_columns(idx)
    missing = [TX_ALIASES[f][0] for f in TX_REQUIRED if at[f] is None]
    if at["pay_amount"] is not None and TX_ALIASES["amount"][0] in missing:
        missing.remove(TX_ALIASES["amount"][0])
    if missing:
        raise WorkbookError(f"Transactions sheet is missing required columns: {missing}")

    def col(row, field):
        i = at[field]
        return row[i] if i is not None and i < len(row) else None

    def text(row, field):
        return _unquote(_s(col(row, field)))

    # a workbook that spells the category out in a column of its own says so in
    # the header; the live spreadsheet leaves it unnamed and has to be found by
    # position, so only look for it when there is no named column to use
    cat_col = at["category"] if at["category"] is not None else _category_col(ws, idx)
    rows = []
    seen = set()
    skipped_status = 0
    foreign: dict[str, int] = {}
    dupes = 0
    for n, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(v is None or _s(v) == "" for v in row):
            continue
        status = _s(col(row, "status")).upper()
        if status not in ("OK", ""):
            skipped_status += 1
            continue
        dt = _parse_dt(col(row, "date"))
        # what actually left the account, not what the bank operation was for:
        # one operation split across categories keeps its original total in the
        # operation amount on every part and carries the real share here
        amount = _amount(col(row, "pay_amount"))
        currency = _s(col(row, "pay_currency"))
        if amount is None:
            amount = _amount(col(row, "amount"))
            currency = _s(col(row, "currency"))
        currency = currency or _s(col(row, "currency"))
        description = text(row, "description")
        if dt is None or amount is None:
            if dt is None and amount is None and not description:
                continue
            errors.append({"row": n, "error": "unparseable date or amount"})
            continue
        currency = (currency or DEFAULT_CURRENCY).upper()
        if currency != DEFAULT_CURRENCY:
            foreign[currency] = foreign.get(currency, 0) + 1
        date_iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        marker = text(row, "card") or text(row, "account")
        key = (date_iso, amount, description, marker, currency)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        category = _unquote(_s(row[cat_col])) if cat_col is not None and cat_col < len(row) else ""
        rows.append(
            {
                "date": date_iso,
                "amount": amount,
                "description": description,
                "bank_category": text(row, "bank_category"),
                "mcc": text(row, "mcc"),
                "comment": text(row, "comment"),
                "monori_category": category,
                "marker": marker,
                "currency": currency,
            }
        )
    if dupes:
        warnings.append(
            f"Transactions: {dupes} rows identical in date, amount, description and card"
            " — kept once"
        )
    if skipped_status:
        warnings.append(f"Transactions: {skipped_status} non-OK rows skipped")
    for code, n in sorted(foreign.items()):
        warnings.append(
            f"Transactions: {n} rows in {code} — they need an account held in {code} to land on"
        )
    return rows


def _known_max_col(idx):
    return max((i for h, i in idx.items() if h in KNOWN_TX_HEADERS), default=-1)


def _find_keyword_block(ws, idx):
    """
    Locates the `category name | pipe-separated keywords` side table by
    content: the column pair (right of the known bank headers) with the most
    rows whose second cell contains a pipe. Purely positional lookup broke on
    the live file — the table starts at row 1, so its own cells pollute the
    header index and shift any fixed offset.
    """
    start = _known_max_col(idx) + 1
    scores: dict[int, int] = {}
    for row in ws.iter_rows(
        min_row=1, max_row=min(ws.max_row, SIDE_TABLE_SCAN_ROWS), values_only=True
    ):
        for base in range(start, len(row) - 1):
            if _s(row[base]) and "|" in _s(row[base + 1]):
                scores[base] = scores.get(base, 0) + 1
    if not scores:
        return None
    return max(scores, key=lambda b: (scores[b], -b))


def _category_col(ws, idx):
    """
    The per-row category lives right of the known bank headers and left of the
    keyword table — but the live template puts *two* columns there: the keyword
    rules compute a guess in the first, and the second either carries that guess
    through or replaces it with what the user typed by hand. Only the second one
    is what the sheet's own totals are built from, so it is the truth: a hand
    label wins outright, and the automatic guess only survives where the user let
    it. Taking the first populated column instead left 56% of the rows here
    uncategorized.

    Picking the fullest column finds it without hardcoding an offset, and still
    works for our own exporter, which writes a single column.
    """
    start = _known_max_col(idx) + 1
    stop = _find_keyword_block(ws, idx)
    if stop is None:
        stop = ws.max_column
    filled: dict[int, int] = {}
    for row in ws.iter_rows(
        min_row=2, max_row=min(ws.max_row, SIDE_TABLE_SCAN_ROWS), values_only=True
    ):
        for c in range(start, min(stop, len(row))):
            if _s(row[c]):
                filled[c] = filled.get(c, 0) + 1
    if not filled:
        return _known_max_col(idx) + 2
    return max(filled, key=lambda c: (filled[c], c))


def _parse_keywords(ws, idx):
    """
    Reads the keyword side table (see _find_keyword_block): category name |
    pipe-separated keywords, starting at row 1.
    """
    base = _find_keyword_block(ws, idx)
    if base is None:
        base = _known_max_col(idx) + 3
    keywords: dict[str, str] = {}
    for row in ws.iter_rows(min_row=1, values_only=True):
        if base >= len(row):
            continue
        name = _s(row[base])
        kws = _s(row[base + 1]) if base + 1 < len(row) else ""
        if name and kws and ("|" in kws or len(kws) > 1):
            keywords.setdefault(name, kws)
    return keywords


def _synthetic(year, month, amount, category, description, marker=""):
    date_iso = _stamp(year, month)
    return {
        "date": date_iso,
        "amount": amount,
        "description": description,
        "bank_category": "",
        "mcc": "",
        "comment": "",
        "monori_category": category,
        "marker": marker,
        "currency": DEFAULT_CURRENCY,
    }


def account_slot(tx):
    """
    Which account a row must land on. A card marker alone is not enough: the
    same marker can carry rows in more than one currency (interest on a foreign
    balance arrives with no card number at all), and an amount only means
    anything on an account held in that currency. Marker and currency together
    are the unit the user maps.
    """
    return f"{tx.get('currency') or DEFAULT_CURRENCY}:{tx['marker']}"


def _last_activity(transactions, sources):
    """
    Last (year, month) showing real activity: a transaction, a nonzero cached
    outflow or income. Budgets deliberately do not count — planning months
    ahead is normal, a budget alone creates no transactions in the sheet, and
    the cached balances of those future months are pure carry residue;
    reconciling against them fabricates future-dated synthetic rows.
    """
    last = None

    def bump(y, m):
        nonlocal last
        if last is None or (y, m) > last:
            last = (y, m)

    # uncategorized transactions are excluded from the reconciliation sums, so
    # they must not extend the reconciled range either
    for tx in transactions:
        if tx["monori_category"]:
            bump(int(tx["date"][:4]), int(tx["date"][5:7]))
    for source in sources:
        y = source["year"]
        for m, v in source["income"].items():
            if v:
                bump(y, m)
        for entry in source["cats"].values():
            for m, v in entry["outflows"].items():
                if v:
                    bump(y, m)
    return last


def _month_range(start, end):
    y, m = start
    while (y, m) <= end:
        yield (y, m)
        m += 1
        if m > 12:
            y, m = y + 1, 1


def parse_workbook(data: bytes):
    """
    Returns {groups, categories, transactions, budgets, warnings, errors} for any
    budget workbook — see the module docstring for how the shape is discovered.
    """
    try:
        wb = load_workbook(BytesIO(data), data_only=True)
    except Exception as exc:
        raise WorkbookError(f"not a readable .xlsx workbook: {exc}") from exc
    try:
        return _parse(wb)
    finally:
        wb.close()


def _parse(wb):
    warnings: list[str] = []
    errors: list[dict] = []
    if spec.SHEET_TRANSACTIONS not in wb.sheetnames:
        raise WorkbookError(f"missing required sheet: {spec.SHEET_TRANSACTIONS}")
    tx_ws = wb[spec.SHEET_TRANSACTIONS]
    tx_idx = _tx_header_index(tx_ws)
    transactions = _parse_transactions(tx_ws, warnings, errors)
    keywords = _parse_keywords(tx_ws, tx_idx)

    archive_years = {}
    live_years = {}
    plain_sheets = {}
    for name in wb.sheetnames:
        year_match = YEAR_RE.match(name)
        if not year_match:
            continue
        ws = wb[name]
        if not hasattr(ws, "iter_rows"):
            continue
        layout = _find_layout(ws)
        if layout is None:
            warnings.append(f"{name}: unrecognized year sheet layout, ignored")
            continue
        year = int(year_match.group(1))
        parsed = _parse_year_sheet(ws, year, layout)
        if year_match.group(2):
            archive_years[year] = parsed
        else:
            plain_sheets[year] = parsed
    for year, parsed in plain_sheets.items():
        if year not in archive_years:
            live_years[year] = parsed
    known_sheets = {spec.SHEET_CATEGORIES, spec.SHEET_TRANSACTIONS, spec.SHEET_DASHDATA}
    for name in wb.sheetnames:
        if name not in known_sheets and not YEAR_RE.match(name):
            warnings.append(f"unknown sheet ignored: {name}")

    first_live = min(live_years) if live_years else None
    seam_year = -1 if first_live is None else first_live - 1
    seam_sheet = plain_sheets.get(seam_year)

    groups: list[dict] = []
    categories: list[dict] = []
    group_names = set()
    cat_names = {}

    def add_group(name, kind, sort=None):
        if name in group_names:
            return
        group_names.add(name)
        groups.append({"name": name, "sort": len(groups) if sort is None else sort, "kind": kind})

    def add_category(name, group, keywords_text=None, group_kind=None, group_sort=0):
        if name in cat_names:
            return
        cat_names[name] = group
        categories.append(
            {
                "group": group,
                "group_kind": group_kind,
                "group_sort": group_sort,
                "name": name,
                "keywords": keywords_text if keywords_text is not None else keywords.get(name, ""),
            }
        )

    # A workbook that states its category structure outright is believed; one
    # that doesn't has it read off the sections of its year grids, which is the
    # only place a hand-kept sheet records it.
    stated_warnings: list[str] = []
    stated_groups, stated_categories = (
        _parse_categories(wb[spec.SHEET_CATEGORIES], stated_warnings)
        if spec.SHEET_CATEGORIES in wb.sheetnames
        else ([], [])
    )
    # a sheet by that name whose rows say nothing this reader recognizes is not
    # a structure sheet at all — the grids know better, and complaining about
    # every row of it would bury the warnings that matter
    if stated_categories:
        warnings.extend(stated_warnings)
    else:
        stated_groups = []
        if stated_warnings:
            warnings.append(
                f"Categories: no category rows recognized ({len(stated_warnings)} rows skipped),"
                " structure taken from the year grids"
            )
    for group in stated_groups:
        add_group(group["name"], group["kind"], group["sort"])
    for cat in stated_categories:
        add_group(cat["group"], cat["group_kind"] or "expense", cat["group_sort"])
        add_category(
            cat["name"], cat["group"], cat["keywords"], cat["group_kind"], cat["group_sort"]
        )

    # ...and when the structure was stated, the grids may not invent categories
    # it left out: a label down the side that no category claims is a leftover
    # or a subtotal, and gets reported rather than imported.
    stated = bool(stated_categories)
    # A grid gives income no section of its own — it is summarised in a header
    # cell per month — so a workbook whose structure never marks a group as
    # income has none, and the income the reconciliation rebuilds needs
    # somewhere to live. Declared before the sections so a category named for it
    # is not swallowed by whichever expense section happens to contain the row.
    all_sections = [
        section
        for years in (live_years, archive_years)
        for year in years
        for section in years[year]["sections"]
    ]
    if not stated and all_sections and not any(s["kind"] == "income" for s in all_sections):
        add_group(INCOME_GROUP, "income")
        add_category(INCOME_CATEGORY, INCOME_GROUP)

    for years in (live_years, archive_years):
        for year in sorted(years, reverse=True):
            for section in years[year]["sections"]:
                if stated:
                    for _, name in section["rows"]:
                        if name not in cat_names:
                            warnings.append(f"{year}: unknown row label skipped: {name[:60]}")
                    continue
                add_group(section["name"], section["kind"])
                for _, name in section["rows"]:
                    add_category(name, section["name"])

    # A category a row names but no structure lists still exists — losing it
    # would silently uncategorize that row. It joins the income side when
    # everything filed under it came in, and the expense side otherwise.
    named_only: dict[str, list] = {}
    for tx in transactions:
        name = tx["monori_category"]
        if name and name not in cat_names:
            named_only.setdefault(name, []).append(tx["amount"])
    if named_only:
        income_group = next((g["name"] for g in groups if g["kind"] == "income"), None)
        expense_group = next((g["name"] for g in groups if g["kind"] != "income"), None)
        for name, amounts in named_only.items():
            if all(a >= 0 for a in amounts):
                if income_group is None:
                    add_group(INCOME_GROUP, "income")
                    income_group = INCOME_GROUP
                add_category(name, income_group)
            else:
                if expense_group is None:
                    add_group(OTHER_GROUP, "expense")
                    expense_group = OTHER_GROUP
                add_category(name, expense_group)

    if not live_years and not archive_years:
        # no grids, so nothing cached to reconcile against: the rows are all there is
        return _result(groups, categories, transactions, [], warnings, errors)

    # where rebuilt income lands: whatever income category the workbook already
    # has, and only failing that a new one
    income_category = next(
        (
            c["name"]
            for c in categories
            if c["name"] == INCOME_CATEGORY or _kind_of(c["group"], groups) == "income"
        ),
        None,
    )
    if income_category is None:
        add_group(INCOME_GROUP, "income")
        add_category(INCOME_CATEGORY, INCOME_GROUP)
        income_category = INCOME_CATEGORY

    kinds = {}
    group_kind = {g["name"]: g["kind"] for g in groups}
    for cat in categories:
        kinds[cat["name"]] = group_kind.get(cat["group"], "expense")

    budgets = []
    for source in list(archive_years.values()) + list(live_years.values()):
        for name, entry in source["cats"].items():
            if name not in cat_names:
                continue
            for m, amount in entry["budgets"].items():
                if amount:
                    budgets.append(
                        {"category": name, "year": source["year"], "month": m, "amount": amount}
                    )

    # A month that carries real rows is never reconciled: the sheet's own
    # cached totals are a summary of those very rows, so any gap between them
    # means this parser read something wrong — inventing a transaction to close
    # it would double the month instead of fixing it. Reconciliation exists for
    # archive years, which hold aggregates and no rows at all.
    real_months = {(int(tx["date"][:4]), int(tx["date"][5:7])) for tx in transactions}

    tx_sums: dict[tuple, int] = {}
    income_sums: dict[tuple, int] = {}
    for tx in transactions:
        cat = tx["monori_category"]
        if not cat:
            continue
        y, m = int(tx["date"][:4]), int(tx["date"][5:7])
        if kinds.get(cat) == "income":
            income_sums[(y, m)] = income_sums.get((y, m), 0) + tx["amount"]
        else:
            tx_sums[(cat, y, m)] = tx_sums.get((cat, y, m), 0) + tx["amount"]

    synthetic = []
    n_hist = n_adjust = n_trusted = 0
    for source in list(archive_years.values()) + list(live_years.values()):
        year = source["year"]
        live = year in live_years
        for m, target in source["income"].items():
            have = income_sums.get((year, m), 0)
            delta = target - have
            if abs(delta) > ADJUST_TOLERANCE_KOP:
                if (year, m) in real_months:
                    n_trusted += 1
                    continue
                synthetic.append(_synthetic(year, m, delta, income_category, income_category))
                income_sums[(year, m)] = have + delta
                if live:
                    n_adjust += 1
                else:
                    n_hist += 1

    budget_map: dict[tuple, int] = {}
    for cell in budgets:
        key = (cell["category"], cell["year"], cell["month"])
        budget_map[key] = budget_map.get(key, 0) + cell["amount"]

    all_years = sorted(set(archive_years) | set(live_years))
    first_sheet = archive_years.get(all_years[0]) or live_years[all_years[0]]
    start = (all_years[0], min(first_sheet["months"]))
    end = (all_years[-1], 12)
    last_active = _last_activity(
        transactions, list(archive_years.values()) + list(live_years.values())
    )
    if last_active is not None and last_active < end:
        end = max(last_active, start)
        if seam_sheet is not None:
            end = max(end, (seam_year, 12))
    expense_cats = [c["name"] for c in categories if kinds[c["name"]] != "income"]

    seam_targets = {}
    if seam_sheet is not None:
        last_m = max(seam_sheet["months"])
        for name, entry in seam_sheet["cats"].items():
            bal = entry["balances"].get(last_m)
            if bal is not None:
                seam_targets[name] = bal
    seam_seed = live_years[first_live]["seed"] if first_live is not None else None

    balances: dict[str, int] = {}
    avail = 0
    prev_overspent = 0
    avail_residuals = []
    n_seam = 0
    for y, m in _month_range(start, end):
        income = income_sums.get((y, m), 0)
        budgeted_total = sum(budget_map.get((name, y, m), 0) for name in cat_names)
        avail = avail + prev_overspent + income - budgeted_total
        live = y in live_years
        source = live_years.get(y) or archive_years.get(y)
        sheet_cats = source["cats"] if source is not None else {}
        at_seam = seam_sheet is not None and (y, m) == (seam_year, 12)
        overspent = 0
        for name in expense_cats:
            carry = max(balances.get(name, 0), 0)
            have = tx_sums.get((name, y, m), 0)
            projected = carry + budget_map.get((name, y, m), 0) + have
            entry = sheet_cats.get(name)
            target = None
            if at_seam:
                if name in seam_targets:
                    target = seam_targets[name]
                elif first_live is not None and name not in live_years[first_live]["cats"]:
                    target = 0
            elif entry is not None:
                target = entry["balances"].get(m)
                if target is None and m in entry["outflows"]:
                    target = projected - have + entry["outflows"][m]
            elif (
                not live
                and balances.get(name, 0) != 0
                and source is not None
                and m == max(source["months"])
            ):
                target = 0
            delta = 0 if target is None else target - projected
            if abs(delta) > ADJUST_TOLERANCE_KOP and (y, m) in real_months:
                n_trusted += 1
                delta = 0
            if abs(delta) > ADJUST_TOLERANCE_KOP:
                if at_seam:
                    n_seam += 1
                elif live:
                    n_adjust += 1
                else:
                    n_hist += 1
                synthetic.append(_synthetic(y, m, delta, name, name))
                tx_sums[(name, y, m)] = have + delta
                projected += delta
            balances[name] = projected
            overspent += min(projected, 0)
        if at_seam and seam_seed is not None and (y, m) not in real_months:
            delta = seam_seed - avail
            if abs(delta) > ADJUST_TOLERANCE_KOP:
                synthetic.append(_synthetic(y, m, delta, income_category, income_category))
                income_sums[(y, m)] = income_sums.get((y, m), 0) + delta
                avail += delta
                n_seam += 1
        prev_overspent = overspent
        if live and source is not None:
            target_avail = source["available"].get(m)
            if target_avail is not None and abs(target_avail - avail) > VERIFY_TOLERANCE_KOP:
                avail_residuals.append((y, m, target_avail - avail))

    if n_hist:
        warnings.append(
            f"history: {n_hist} transactions stand in for months the sheet keeps only as monthly"
            " totals (the archive years have no rows) — one per category per month, so those"
            " years still add up"
        )
    if n_adjust:
        warnings.append(
            f"reconciliation: {n_adjust} adjustment transactions align live months with the sheet"
        )
    if n_seam:
        warnings.append(f"seam: {n_seam} carry corrections at {seam_year}-12")
    if n_trusted:
        warnings.append(
            f"reconciliation: in {n_trusted} category-months the total written in the sheet is not"
            " what its own rows add up to (a hand-edited cell, usually) — the rows win, nothing"
            " was added to close the gap"
        )
    if avail_residuals:
        (fy, fm, fd), (ly, lm, ld) = avail_residuals[0], avail_residuals[-1]
        warnings.append(
            f"verify: the sheet's own Available differs from the one rebuilt from its rows in "
            f"{len(avail_residuals)} months, from {fd / 100:,.2f} ({fy}-{fm:02d}) to "
            f"{ld / 100:,.2f} ({ly}-{lm:02d}) — a difference this steady is money carried in from "
            "before the earliest sheet; transactions and budgets are imported either way"
        )

    return _result(groups, categories, transactions + synthetic, budgets, warnings, errors)


def _result(groups, categories, transactions, budgets, warnings, errors):
    return {
        "groups": [{"name": g["name"], "sort": g["sort"], "kind": g["kind"]} for g in groups],
        "categories": categories,
        "transactions": transactions,
        "budgets": budgets,
        "warnings": warnings,
        "errors": errors,
    }
