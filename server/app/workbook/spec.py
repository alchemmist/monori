GLYPH_IN = "▲"
GLYPH_OUT = "▼"

SHEET_CATEGORIES = "Categories"
SHEET_TRANSACTIONS = "Transactions"
SHEET_DASHDATA = "DashData"

CATEGORY_HEADERS = ["Sort Order", "Category Group", "Category", "Keywords"]
GROUP_HEADERS = ["Category Group", "Sort Order", "Type"]

TRANSACTION_HEADERS = [
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

MONTHS = [
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
MONTH_COLS = ["Budgeted", "Outflows", "Balance"]

DASH_HEADERS = ["Month", "Income", "Expense", "Ratio", "CumNet"]

TYPE_IN = "IN"
TYPE_OUT = "OUT"

MONEY_FORMAT = "0.00"


def kop_to_rub(kop: int) -> float:
    return round(kop / 100, 2)


def group_display(name: str, kind: str) -> str:
    glyph = GLYPH_IN if kind == "income" else GLYPH_OUT
    return f"{glyph}{name}"


def group_type(kind: str) -> str:
    return TYPE_IN if kind == "income" else TYPE_OUT
