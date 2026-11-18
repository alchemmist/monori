# Copyright (c) 2026
"""
Exchange rates: what a unit of a currency was worth on a given day.

Every rate is quoted against a single pivot (RUB), so the table stays one row
per currency per day and any A→B conversion is ``amount * rate(A) / rate(B)``.
Rates come from the Bank of Russia's daily feed, can be overridden by hand, and
fall back to a bundled snapshot when neither is available — an app that cannot
reach the internet still has to add up.

A conversion is always resolved against the transaction's own date and frozen
onto the row as ``base_amount``. Rates published later never rewrite history.
"""

import re
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from datetime import date as date_cls
from typing import TypedDict, cast

import httpx

from .currencies import CURRENCIES, PIVOT_CURRENCY, normalize

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
CBR_TIMEOUT = 10.0

SOURCE_CBR = "cbr"
SOURCE_MANUAL = "manual"
SOURCE_BUNDLED = "bundled"

BUNDLED_DAY = "2025-07-01"
BUNDLED_RATES = {
    "RUB": 1.0,
    "USD": 78.5,
    "EUR": 92.4,
    "GBP": 107.6,
    "CHF": 98.7,
    "KZT": 0.1512,
    "BYN": 26.72,
    "GEL": 28.94,
    "AMD": 0.2043,
    "TRY": 1.977,
    "AED": 21.37,
    "CNY": 10.95,
    "RSD": 0.7885,
}

VALUTE_SPLIT = re.compile(r"<Valute\b")
CHAR_CODE_RE = re.compile(r"<CharCode>\s*([A-Za-z]{3})\s*</CharCode>")
NOMINAL_RE = re.compile(r"<Nominal>\s*([\d ]{1,12})\s*</Nominal>")
VALUE_RE = re.compile(r"<Value>\s*([\d]{1,15}[.,][\d]{1,6})\s*</Value>")


class RateUnavailableError(Exception):
    """Raised when no rate is known for a currency on the requested day."""


class RateTableEntry(TypedDict):
    """Represent one dated exchange-rate response row."""

    code: str
    rate: float
    day: str
    source: str
    stale: bool


def today_iso() -> str:
    """Return today's UTC calendar date."""
    return datetime.now(UTC).date().isoformat()


def parse_cbr(payload: str) -> dict[str, float]:
    """
    Pull ``code -> rubles per unit`` out of a CBR daily feed.

    The feed quotes a ``Value`` per ``Nominal`` units (10 000 AMD, 100 KZT), so
    the division is what makes the numbers comparable.
    """
    rates = {}
    for chunk in VALUTE_SPLIT.split(payload)[1:]:
        code = CHAR_CODE_RE.search(chunk)
        nominal = NOMINAL_RE.search(chunk)
        value = VALUE_RE.search(chunk)
        if not (code and nominal and value):
            continue
        units = int(nominal.group(1).replace(" ", "") or 1)
        if units <= 0:
            continue
        rates[code.group(1).upper()] = float(value.group(1).replace(",", ".")) / units
    return rates


def fetch_cbr(day: str | None = None, client: httpx.Client | None = None) -> dict[str, float]:
    """
    Fetch the CBR rates for ``day`` (ISO date, today when omitted).

    The feed only moves on business days and answers a weekend request with the
    previous publication, which is exactly the rate that was in force — so the
    response is stored under the day that was asked for.
    """
    day = day or today_iso()
    y, m, d = day[:10].split("-")
    params = {"date_req": f"{d}/{m}/{y}"}
    if client is None:
        with httpx.Client(timeout=CBR_TIMEOUT) as owned:
            response = owned.get(CBR_URL, params=params)
    else:
        response = client.get(CBR_URL, params=params)
    response.raise_for_status()
    return parse_cbr(response.text)


def store_rates(
    c: sqlite3.Connection,
    day: str,
    rates: Mapping[str, float],
    source: str = SOURCE_CBR,
) -> int:
    """
    Upsert ``code -> rubles per unit`` for ``day``. Codes monori does not offer.

    are dropped: the feed carries forty of them and none of the rest can ever
    be attached to an account.
    """
    kept = 0
    for raw_code, per_unit in rates.items():
        code = normalize(raw_code, "")
        if code not in CURRENCIES or code == PIVOT_CURRENCY or per_unit <= 0:
            continue
        values = (day[:10], code, float(per_unit), source)
        if source == SOURCE_MANUAL:
            c.execute(
                "INSERT INTO exchange_rates (day, code, rub_per_unit, source) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(day, code) DO UPDATE SET"
                " rub_per_unit=excluded.rub_per_unit, source=excluded.source",
                values,
            )
        else:
            c.execute(
                "INSERT INTO exchange_rates (day, code, rub_per_unit, source) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(day, code) DO UPDATE SET"
                " rub_per_unit=excluded.rub_per_unit, source=excluded.source"
                " WHERE exchange_rates.source != 'manual'",
                values,
            )
        kept += 1
    return kept


def refresh(
    c: sqlite3.Connection,
    day: str | None = None,
    client: httpx.Client | None = None,
) -> int:
    """
    Fetch and store one day of rates, returning how many were kept.
    """
    day = (day or today_iso())[:10]
    return store_rates(c, day, fetch_cbr(day, client=client))


def stored_rate(c: sqlite3.Connection, code: str, day: str) -> sqlite3.Row | None:
    """
    Return the stored rate in force on ``day``.
    """
    return cast(
        "sqlite3.Row | None",
        c.execute(
            "SELECT day, rub_per_unit, source FROM exchange_rates"
            " WHERE code=? AND day<=? ORDER BY day DESC LIMIT 1",
            (code, day[:10]),
        ).fetchone(),
    )


def rate_on(c: sqlite3.Connection, code: str, day: str) -> tuple[float, str, str]:
    """
    Rubles per unit of ``code`` on ``day``, as ``(rate, day, source)``.
    """
    code = normalize(code)
    if code == PIVOT_CURRENCY:
        return 1.0, day[:10], "pivot"
    row = stored_rate(c, code, day)
    if row is not None:
        return float(row["rub_per_unit"]), row["day"], row["source"]
    if code in BUNDLED_RATES and day[:10] >= BUNDLED_DAY:
        return BUNDLED_RATES[code], BUNDLED_DAY, SOURCE_BUNDLED
    message = f"no exchange rate for {code}"
    raise RateUnavailableError(message)


def convert(c: sqlite3.Connection, amount: int, src: str, dst: str, day: str) -> int:
    """
    ``amount`` minor units of ``src`` expressed in minor units of ``dst``, at.

    the rates in force on ``day``. Same currency is an exact identity — no
    float ever touches money that does not need converting.
    """
    src = normalize(src)
    dst = normalize(dst)
    if src == dst:
        return amount
    src_rate, _, _ = rate_on(c, src, day)
    dst_rate, _, _ = rate_on(c, dst, day)
    return round(amount * src_rate / dst_rate)


def rate_table(
    c: sqlite3.Connection, day: str | None = None
) -> list[dict[str, str | float | bool]]:
    """
    One entry per known currency for ``day``, for the settings screen: the rate.

    itself, the day it was actually published, and where it came from.
    """
    day = (day or today_iso())[:10]
    table: list[RateTableEntry] = []
    for code in CURRENCIES:
        try:
            rate, on, source = rate_on(c, code, day)
        except RateUnavailableError:
            continue
        table.append({"code": code, "rate": rate, "day": on, "source": source, "stale": on != day})
    return cast("list[dict[str, str | float | bool]]", table)


def missing_days(c: sqlite3.Connection, days_back: int = 30, today: str | None = None) -> list[str]:
    """
    Return recent days with no stored rates at all.

    These are what a catch-up refresh has
    to fetch, newest first.
    """
    current_day = date_cls.fromisoformat((today or today_iso())[:10])
    have = {
        r["day"]
        for r in c.execute(
            "SELECT DISTINCT day FROM exchange_rates WHERE day>=?",
            ((current_day - timedelta(days=days_back)).isoformat(),),
        )
    }
    return [
        d.isoformat()
        for d in (current_day - timedelta(days=n) for n in range(days_back + 1))
        if d.isoformat() not in have
    ]


def backfill(
    c: sqlite3.Connection,
    days_back: int = 30,
    today: str | None = None,
    client: httpx.Client | None = None,
) -> int:
    """
    Fetch every recent day we are missing. Network failures stop the sweep.

    rather than abort it — whatever was already stored stays stored.
    """
    fetched = 0
    for day in missing_days(c, days_back, today):
        try:
            refresh(c, day, client=client)
        except (httpx.HTTPError, sqlite3.Error):
            break
        fetched += 1
    return fetched
