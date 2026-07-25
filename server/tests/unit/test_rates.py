import pathlib
import sys

import httpx
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import app.db as dbmod
from app.rates import (
    BUNDLED_DAY,
    BUNDLED_RATES,
    SOURCE_BUNDLED,
    SOURCE_MANUAL,
    RateUnavailable,
    backfill,
    convert,
    fetch_cbr,
    missing_days,
    parse_cbr,
    rate_on,
    rate_table,
    refresh,
    store_rates,
)

FEED = """<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="01.07.2025" name="Foreign Currency Market">
<Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode><Nominal>1</Nominal>
<Name>Доллар США</Name><Value>78,5000</Value><VunitRate>78,5</VunitRate></Valute>
<Valute ID="R01239"><NumCode>978</NumCode><CharCode>EUR</CharCode><Nominal>1</Nominal>
<Name>Евро</Name><Value>92,4000</Value><VunitRate>92,4</VunitRate></Valute>
<Valute ID="R01060"><NumCode>051</NumCode><CharCode>AMD</CharCode><Nominal>100</Nominal>
<Name>Армянских драмов</Name><Value>20,4300</Value><VunitRate>0,2043</VunitRate></Valute>
<Valute ID="R01500"><NumCode>392</NumCode><CharCode>JPY</CharCode><Nominal>100</Nominal>
<Name>Иен</Name><Value>54,3000</Value><VunitRate>0,543</VunitRate></Valute>
</ValCurs>
"""


def _db(tmp_path):
    return dbmod.connect(str(tmp_path / "rates.db"))


class _Feed:
    """
    A stand-in for the CBR: answers with a fixed payload and records the dates
    it was asked for.
    """

    def __init__(self, payload=FEED, fail=False):
        self.payload = payload
        self.fail = fail
        self.asked = []

    def get(self, url, params=None):
        self.asked.append((params or {}).get("date_req"))
        if self.fail:
            raise httpx.ConnectError("offline")
        return httpx.Response(200, text=self.payload, request=httpx.Request("GET", url))


def test_parse_cbr_divides_by_the_nominal():
    rates = parse_cbr(FEED)
    assert rates["USD"] == 78.5
    assert rates["EUR"] == 92.4
    # quoted per 100 units, so the per-unit rate is two orders smaller
    assert rates["AMD"] == pytest.approx(0.2043)


def test_parse_cbr_ignores_junk():
    assert parse_cbr("") == {}
    assert parse_cbr("<ValCurs><Valute><CharCode>USD</CharCode></Valute></ValCurs>") == {}


def test_parse_cbr_refuses_to_divide_by_a_zero_nominal():
    feed = (
        "<ValCurs><Valute><CharCode>USD</CharCode><Nominal>0</Nominal>"
        "<Value>78,5000</Value></Valute></ValCurs>"
    )
    assert parse_cbr(feed) == {}


def test_parse_cbr_reads_a_blank_nominal_as_one():
    feed = (
        "<ValCurs><Valute><CharCode>USD</CharCode><Nominal> </Nominal>"
        "<Value>78,5000</Value></Valute></ValCurs>"
    )
    assert parse_cbr(feed) == {"USD": 78.5}


def test_store_rates_keeps_only_currencies_monori_offers(tmp_path):
    c = _db(tmp_path)
    try:
        kept = store_rates(c, "2025-07-01", parse_cbr(FEED))
        # JPY is in the feed but not on the list, and RUB is the pivot itself
        assert kept == 3
        codes = {r["code"] for r in c.execute("SELECT code FROM exchange_rates")}
        assert codes == {"USD", "EUR", "AMD"}
    finally:
        c.close()


def test_store_rates_rejects_nonsense(tmp_path):
    c = _db(tmp_path)
    try:
        assert store_rates(c, "2025-07-01", {"USD": 0, "EUR": -1, "RUB": 1.0}) == 0
    finally:
        c.close()


def test_store_rates_overwrites_the_same_day(tmp_path):
    c = _db(tmp_path)
    try:
        store_rates(c, "2025-07-01", {"USD": 78.5})
        store_rates(c, "2025-07-01", {"USD": 80.0}, source=SOURCE_MANUAL)
        rate, day, source = rate_on(c, "USD", "2025-07-01")
        assert (rate, day, source) == (80.0, "2025-07-01", SOURCE_MANUAL)
    finally:
        c.close()


def test_rate_on_pivot_is_exactly_one(tmp_path):
    c = _db(tmp_path)
    try:
        assert rate_on(c, "RUB", "2025-07-01") == (1.0, "2025-07-01", "pivot")
    finally:
        c.close()


def test_rate_on_uses_the_latest_publication_not_later_than_the_day(tmp_path):
    c = _db(tmp_path)
    try:
        store_rates(c, "2025-07-01", {"USD": 78.5})
        store_rates(c, "2025-07-10", {"USD": 80.0})
        assert rate_on(c, "USD", "2025-07-05")[:2] == (78.5, "2025-07-01")
        assert rate_on(c, "USD", "2025-07-10")[:2] == (80.0, "2025-07-10")
        assert rate_on(c, "USD", "2026-01-01")[:2] == (80.0, "2025-07-10")
    finally:
        c.close()


def test_rate_on_reaches_forward_for_a_transaction_older_than_any_rate(tmp_path):
    c = _db(tmp_path)
    try:
        store_rates(c, "2025-07-01", {"USD": 78.5})
        assert rate_on(c, "USD", "2020-01-01")[:2] == (78.5, "2025-07-01")
    finally:
        c.close()


def test_rate_on_falls_back_to_the_bundled_snapshot(tmp_path):
    c = _db(tmp_path)
    try:
        rate, day, source = rate_on(c, "GEL", "2026-07-01")
        assert (day, source) == (BUNDLED_DAY, SOURCE_BUNDLED)
        assert rate > 0
    finally:
        c.close()


def test_rate_on_raises_for_a_currency_nobody_quotes(tmp_path):
    c = _db(tmp_path)
    try:
        with pytest.raises(RateUnavailable):
            rate_on(c, "XYZ", "2026-07-01")
    finally:
        c.close()


def test_convert_is_an_exact_identity_within_one_currency(tmp_path):
    c = _db(tmp_path)
    try:
        # no rounding, no float — 7 kopecks stay 7 kopecks
        assert convert(c, 7, "USD", "USD", "2026-07-01") == 7
        assert convert(c, -12345, "gel", "GEL", "2026-07-01") == -12345
    finally:
        c.close()


def test_convert_goes_through_the_pivot(tmp_path):
    c = _db(tmp_path)
    try:
        store_rates(c, "2026-07-01", {"USD": 80.0, "EUR": 100.0})
        # 100.00 USD = 8000 RUB = 80.00 EUR
        assert convert(c, 10000, "USD", "EUR", "2026-07-01") == 8000
        assert convert(c, 10000, "USD", "RUB", "2026-07-01") == 800000
        assert convert(c, 800000, "RUB", "USD", "2026-07-01") == 10000
    finally:
        c.close()


def test_convert_keeps_the_sign_and_rounds_to_the_minor_unit(tmp_path):
    c = _db(tmp_path)
    try:
        store_rates(c, "2026-07-01", {"USD": 78.53})
        assert convert(c, -10000, "USD", "RUB", "2026-07-01") == -785300
        assert convert(c, 1, "USD", "RUB", "2026-07-01") == 79
    finally:
        c.close()


def test_rate_table_flags_a_stale_quote(tmp_path):
    c = _db(tmp_path)
    try:
        store_rates(c, "2026-06-01", {"USD": 80.0})
        table = {r["code"]: r for r in rate_table(c, "2026-07-01")}
        assert table["USD"]["stale"] is True
        assert table["USD"]["day"] == "2026-06-01"
        assert table["RUB"]["stale"] is False
    finally:
        c.close()


def test_refresh_stores_the_day_that_was_asked_for(tmp_path):
    c = _db(tmp_path)
    feed = _Feed()
    try:
        assert refresh(c, "2025-07-06", client=feed) == 3
        # a Sunday: the feed answers with Friday's numbers, and those are the
        # rates that were in force on Sunday
        assert feed.asked == ["06/07/2025"]
        assert rate_on(c, "USD", "2025-07-06")[:2] == (78.5, "2025-07-06")
    finally:
        c.close()


def test_missing_days_lists_only_the_gaps(tmp_path):
    c = _db(tmp_path)
    try:
        store_rates(c, "2026-07-24", {"USD": 80.0})
        gaps = missing_days(c, days_back=2, today="2026-07-25")
        assert gaps == ["2026-07-25", "2026-07-23"]
    finally:
        c.close()


def test_backfill_fetches_every_gap(tmp_path):
    c = _db(tmp_path)
    feed = _Feed()
    try:
        assert backfill(c, days_back=2, today="2026-07-25", client=feed) == 3
        assert feed.asked == ["25/07/2026", "24/07/2026", "23/07/2026"]
    finally:
        c.close()


def test_backfill_stops_at_the_first_network_failure(tmp_path):
    c = _db(tmp_path)
    feed = _Feed(fail=True)
    try:
        assert backfill(c, days_back=5, today="2026-07-25", client=feed) == 0
        assert c.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0] == 0
    finally:
        c.close()


def test_fetch_cbr_opens_its_own_client_when_not_given_one(monkeypatch):
    """
    The refresh endpoint hands its own client in; a script calling fetch_cbr()
    bare must still get a connection, and must still close it.
    """
    closed = []

    class _Client:
        def __init__(self, timeout=None):
            self.timeout = timeout

        def __enter__(self):
            return _Feed()

        def __exit__(self, *exc):
            closed.append(True)
            return False

    monkeypatch.setattr(httpx, "Client", _Client)
    assert fetch_cbr("2025-07-01")["USD"] == 78.5
    assert closed == [True]


def test_rate_table_skips_a_currency_nothing_quotes(tmp_path, monkeypatch):
    """
    A currency added to the registry before any rate exists for it is left out
    of the table rather than shown as a number nobody can stand behind.
    """
    c = _db(tmp_path)
    monkeypatch.delitem(BUNDLED_RATES, "GEL")
    try:
        assert "GEL" not in {r["code"] for r in rate_table(c, "2026-07-01")}
    finally:
        c.close()
