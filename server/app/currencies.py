"""
The currencies monori knows about.

Deliberately a short, curated list rather than all of ISO 4217: every code here
is one a monori user plausibly holds money in, and every one of them has two
minor units. That second property is what lets the whole codebase keep storing
money as an integer count of minor units ("kopecks") and treat the currency as a
label on top — no per-currency scaling anywhere.

``web/src/currencies.js`` is the same list on the frontend; the two are kept in
step by ``tests/unit/test_currencies.py``.
"""

from fastapi import HTTPException

MINOR_UNITS = 2

# code -> (english name, symbol)
CURRENCIES = {
    "RUB": ("Russian ruble", "₽"),
    "USD": ("US dollar", "$"),
    "EUR": ("Euro", "€"),
    "GBP": ("Pound sterling", "£"),
    "CHF": ("Swiss franc", "CHF"),
    "KZT": ("Kazakhstani tenge", "₸"),
    "BYN": ("Belarusian ruble", "Br"),
    "GEL": ("Georgian lari", "₾"),
    "AMD": ("Armenian dram", "֏"),
    "TRY": ("Turkish lira", "₺"),
    "AED": ("UAE dirham", "AED"),
    "CNY": ("Chinese yuan", "¥"),
    "RSD": ("Serbian dinar", "RSD"),
}

DEFAULT_CURRENCY = "RUB"

# every rate is quoted against this one, so a conversion is always two hops at
# most and the rate table stays one row per currency per day
PIVOT_CURRENCY = "RUB"


def normalize(code, fallback=DEFAULT_CURRENCY):
    """
    Trim and upper-case a currency code, falling back when it is missing.
    Unknown codes are returned as given — validation is a separate decision, so
    data that predates the registry can still be read back.
    """
    code = (code or "").strip().upper()
    return code or fallback


def is_known(code):
    return normalize(code, "") in CURRENCIES


def validate(code, fallback=DEFAULT_CURRENCY):
    """
    Normalize a code coming from a request, rejecting anything not on the list.
    """
    normalized = normalize(code, fallback)
    if normalized not in CURRENCIES:
        raise HTTPException(400, f"unknown currency {normalized!r}")
    return normalized


def symbol(code):
    entry = CURRENCIES.get(normalize(code, ""))
    return entry[1] if entry else normalize(code, "")


def catalog():
    """
    The registry as the API serves it.
    """
    return [
        {"code": code, "name": name, "symbol": sym, "minorUnits": MINOR_UNITS}
        for code, (name, sym) in CURRENCIES.items()
    ]
