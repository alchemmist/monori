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
from datetime import date as date_cls
from datetime import timedelta

import httpx

from .currencies import CURRENCIES, PIVOT_CURRENCY, normalize

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
CBR_TIMEOUT = 10.0

SOURCE_CBR = "cbr"
SOURCE_MANUAL = "manual"
SOURCE_BUNDLED = "bundled"

# Rubles per unit, as published by the CBR on BUNDLED_DAY. Only ever used when
# the table has nothing at all for a currency: an offline monori still converts,
# and every response says which day the number is from so a stale one is
# recognizable rather than silently believed.
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

# one <Valute> block of the CBR feed; matched tag by tag over an already-split
# chunk, so the scan stays linear and no XML parser is pointed at the network
VALUTE_SPLIT = re.compile(r"<Valute\b")
CHAR_CODE_RE = re.compile(r"<CharCode>\s*([A-Za-z]{3})\s*</CharCode>")
NOMINAL_RE = re.compile(r"<Nominal>\s*([\d ]{1,12})\s*</Nominal>")
VALUE_RE = re.compile(r"<Value>\s*([\d]{1,15}[.,][\d]{1,6})\s*</Value>")


class RateUnavailable(Exception):
    """
    No rate is known for this currency on this day, from any source.
    """


def today_iso():
    return date_cls.today().isoformat()


def parse_cbr(payload):
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


def fetch_cbr(day=None, client=None):
    """
    The CBR rates for ``day`` (ISO date, today when omitted).

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


def store_rates(c, day, rates, source=SOURCE_CBR):
    """
    Upsert ``code -> rubles per unit`` for ``day``. Codes monori does not offer
    are dropped: the feed carries forty of them and none of the rest can ever
    be attached to an account.
    """
    kept = 0
    for code, per_unit in rates.items():
        code = normalize(code, "")
        if code not in CURRENCIES or code == PIVOT_CURRENCY or per_unit <= 0:
            continue
        c.execute(
            "INSERT INTO exchange_rates (day, code, rub_per_unit, source) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(day, code) DO UPDATE SET"
            " rub_per_unit=excluded.rub_per_unit, source=excluded.source",
            (day[:10], code, float(per_unit), source),
        )
        kept += 1
    return kept


def refresh(c, day=None, client=None):
    """
    Fetch and store one day of rates, returning how many were kept.
    """
    day = (day or today_iso())[:10]
    return store_rates(c, day, fetch_cbr(day, client=client))


def stored_rate(c, code, day):
    """
    The stored rate in force on ``day``: the latest publication no later than
    it, or — for a transaction older than anything we hold — the earliest one
    we have, since an approximate rate beats refusing to show a total.
    """
    row = c.execute(
        "SELECT day, rub_per_unit, source FROM exchange_rates"
        " WHERE code=? AND day<=? ORDER BY day DESC LIMIT 1",
        (code, day[:10]),
    ).fetchone()
    if row is None:
        row = c.execute(
            "SELECT day, rub_per_unit, source FROM exchange_rates"
            " WHERE code=? ORDER BY day ASC LIMIT 1",
            (code,),
        ).fetchone()
    return row


def rate_on(c, code, day):
    """
    Rubles per unit of ``code`` on ``day``, as ``(rate, day, source)``.
    """
    code = normalize(code)
    if code == PIVOT_CURRENCY:
        return 1.0, day[:10], "pivot"
    row = stored_rate(c, code, day)
    if row is not None:
        return float(row["rub_per_unit"]), row["day"], row["source"]
    if code in BUNDLED_RATES:
        return BUNDLED_RATES[code], BUNDLED_DAY, SOURCE_BUNDLED
    raise RateUnavailable(f"no exchange rate for {code}")


def convert(c, amount, src, dst, day):
    """
    ``amount`` minor units of ``src`` expressed in minor units of ``dst``, at
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


def rate_table(c, day=None):
    """
    One entry per known currency for ``day``, for the settings screen: the rate
    itself, the day it was actually published, and where it came from.
    """
    day = (day or today_iso())[:10]
    table = []
    for code in CURRENCIES:
        try:
            rate, on, source = rate_on(c, code, day)
        except RateUnavailable:
            continue
        table.append({"code": code, "rate": rate, "day": on, "source": source, "stale": on != day})
    return table


def missing_days(c, days_back=30, today=None):
    """
    The recent days with no stored rates at all — what a catch-up refresh has
    to fetch, newest first.
    """
    today = date_cls.fromisoformat((today or today_iso())[:10])
    have = {
        r["day"]
        for r in c.execute(
            "SELECT DISTINCT day FROM exchange_rates WHERE day>=?",
            ((today - timedelta(days=days_back)).isoformat(),),
        )
    }
    return [
        d.isoformat()
        for d in (today - timedelta(days=n) for n in range(days_back + 1))
        if d.isoformat() not in have
    ]


def backfill(c, days_back=30, today=None, client=None):
    """
    Fetch every recent day we are missing. Network failures stop the sweep
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
