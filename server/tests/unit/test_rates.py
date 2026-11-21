# Copyright (c) 2026
import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Never

import httpx
import pytest

import monori.server.app.db as dbmod
from monori.server.app.rates import (
    BUNDLED_DAY,
    BUNDLED_RATES,
    CBR_TIMEOUT,
    SOURCE_BUNDLED,
    SOURCE_CBR,
    SOURCE_MANUAL,
    RateUnavailableError,
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

FEED = """
<?xml version="1.0" encoding="windows-1251"?>
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


def _db(tmp_path: Path) -> sqlite3.Connection:
    return dbmod.connect(str(tmp_path / "rates.db"))


class _Feed:
    """Serve a fixed CBR payload and record the requested dates."""

    def __init__(self, payload: str = FEED, *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail
        self.asked: list[str | None] = []
        self.params: list[dict[str, str] | None] = []

    def get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        self.params.append(params)
        self.asked.append((params or {}).get("date_req"))
        if self.fail:
            msg = "offline"
            raise httpx.ConnectError(msg)
        return httpx.Response(200, text=self.payload, request=httpx.Request("GET", url))


def _unexpected_client(*, timeout: float) -> Never:
    """Fail when code discards the client supplied by its caller."""
    message = f"unexpected internal HTTP client (timeout={timeout})"
    raise AssertionError(message)


def test_parse_cbr_divides_by_the_nominal() -> None:
    rates = parse_cbr(FEED)
    assert rates["USD"] == 78.5
    assert rates["EUR"] == 92.4

    assert rates["AMD"] == pytest.approx(0.2043)


def test_parse_cbr_ignores_junk() -> None:
    assert parse_cbr("") == {}
    assert parse_cbr("<ValCurs><Valute><CharCode>USD</CharCode></Valute></ValCurs>") == {}


def test_parse_cbr_needs_all_three_fields() -> None:
    """Skip incomplete currency blocks without discarding later valid ones."""
    feed = (
        "<ValCurs>"
        "<Valute><CharCode>USD</CharCode><Nominal>1</Nominal></Valute>"
        "<Valute><Nominal>1</Nominal><Value>92,4000</Value></Valute>"
        "<Valute><CharCode>EUR</CharCode><Nominal>1</Nominal>"
        "<Value>92,4000</Value></Valute>"
        "</ValCurs>"
    )
    assert parse_cbr(feed) == {"EUR": 92.4}


def test_parse_cbr_refuses_to_divide_by_a_zero_nominal() -> None:
    feed = (
        "<ValCurs><Valute><CharCode>USD</CharCode><Nominal>0</Nominal>"
        "<Value>78,5000</Value></Valute></ValCurs>"
    )
    assert parse_cbr(feed) == {}


def test_parse_cbr_keeps_reading_past_an_unusable_nominal() -> None:
    feed = (
        "<ValCurs>"
        "<Valute><CharCode>USD</CharCode><Nominal>0</Nominal>"
        "<Value>78,5000</Value></Valute>"
        "<Valute><CharCode>EUR</CharCode><Nominal>1</Nominal>"
        "<Value>92,4000</Value></Valute>"
        "</ValCurs>"
    )
    assert parse_cbr(feed) == {"EUR": 92.4}


def test_parse_cbr_reads_a_blank_nominal_as_one() -> None:
    feed = (
        "<ValCurs><Valute><CharCode>USD</CharCode><Nominal> </Nominal>"
        "<Value>78,5000</Value></Valute></ValCurs>"
    )
    assert parse_cbr(feed) == {"USD": 78.5}


def test_store_rates_keeps_only_currencies_monori_offers(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        kept = store_rates(c, "2025-07-01", parse_cbr(FEED))

        assert kept == 3
        codes = {r["code"] for r in c.execute("SELECT code FROM exchange_rates")}
        assert codes == {"USD", "EUR", "AMD"}
    finally:
        c.close()


def test_store_rates_rejects_nonsense(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        assert store_rates(c, "2025-07-01", {"USD": 0, "EUR": -1, "RUB": 1.0}) == 0
    finally:
        c.close()


def test_store_rates_overwrites_the_same_day(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        store_rates(c, "2025-07-01", {"USD": 78.5})
        store_rates(c, "2025-07-01", {"USD": 80.0}, source=SOURCE_MANUAL)
        rate, day, source = rate_on(c, "USD", "2025-07-01")
        assert (rate, day, source) == (80.0, "2025-07-01", SOURCE_MANUAL)
    finally:
        c.close()


def test_rate_on_pivot_is_exactly_one(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        assert rate_on(c, "RUB", "2025-07-01") == (1.0, "2025-07-01", "pivot")
    finally:
        c.close()


def test_rate_on_uses_the_latest_publication_not_later_than_the_day(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        store_rates(c, "2025-07-01", {"USD": 78.5})
        store_rates(c, "2025-07-10", {"USD": 80.0})
        assert rate_on(c, "USD", "2025-07-05")[:2] == (78.5, "2025-07-01")
        assert rate_on(c, "USD", "2025-07-10")[:2] == (80.0, "2025-07-10")
        assert rate_on(c, "USD", "2026-01-01")[:2] == (80.0, "2025-07-10")
    finally:
        c.close()


def test_rate_on_does_not_reach_forward_for_an_older_transaction(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        store_rates(c, "2025-07-01", {"USD": 78.5})
        with pytest.raises(RateUnavailableError):
            rate_on(c, "USD", "2020-01-01")
    finally:
        c.close()


def test_rate_on_falls_back_to_the_bundled_snapshot(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        rate, day, source = rate_on(c, "GEL", "2026-07-01")
        assert (day, source) == (BUNDLED_DAY, SOURCE_BUNDLED)
        assert rate > 0
    finally:
        c.close()


def test_rate_on_raises_for_a_currency_nobody_quotes(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        with pytest.raises(RateUnavailableError):
            rate_on(c, "XYZ", "2026-07-01")
    finally:
        c.close()


def test_convert_is_an_exact_identity_within_one_currency(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        assert convert(c, 7, "USD", "USD", "2026-07-01") == 7
        assert convert(c, -12345, "gel", "GEL", "2026-07-01") == -12345
    finally:
        c.close()


def test_convert_goes_through_the_pivot(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        store_rates(c, "2026-07-01", {"USD": 80.0, "EUR": 100.0})

        assert convert(c, 10000, "USD", "EUR", "2026-07-01") == 8000
        assert convert(c, 10000, "USD", "RUB", "2026-07-01") == 800000
        assert convert(c, 800000, "RUB", "USD", "2026-07-01") == 10000
    finally:
        c.close()


def test_convert_keeps_the_sign_and_rounds_to_the_minor_unit(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        store_rates(c, "2026-07-01", {"USD": 78.53})
        assert convert(c, -10000, "USD", "RUB", "2026-07-01") == -785300
        assert convert(c, 1, "USD", "RUB", "2026-07-01") == 79
    finally:
        c.close()


def test_rate_table_flags_a_stale_quote(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        store_rates(c, "2026-06-01", {"USD": 80.0})
        table = {r["code"]: r for r in rate_table(c, "2026-07-01")}
        assert table["USD"]["stale"] is True
        assert table["USD"]["day"] == "2026-06-01"
        assert table["USD"]["source"] == SOURCE_CBR
        assert table["RUB"]["stale"] is False

        same = {r["code"]: r for r in rate_table(c, "2026-06-01T10:00:00")}
        assert same["USD"]["stale"] is False
    finally:
        c.close()


def test_refresh_preserves_the_feed_publication_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = _db(tmp_path)
    feed = _Feed()
    monkeypatch.setattr(httpx, "Client", _unexpected_client)
    try:
        assert refresh(c, "2025-07-06", client=feed) == 3

        assert feed.asked == ["06/07/2025"]
        assert rate_on(c, "USD", "2025-07-06")[:2] == (78.5, "2025-07-01")
    finally:
        c.close()


def test_missing_days_looks_a_month_back_by_default(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        assert len(missing_days(c, today="2026-07-25")) == 31
    finally:
        c.close()


def test_missing_days_lists_only_the_gaps(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        store_rates(c, "2026-07-24", {"USD": 80.0})
        gaps = missing_days(c, days_back=2, today="2026-07-25")
        assert gaps == ["2026-07-25", "2026-07-23"]
    finally:
        c.close()


def test_backfill_fetches_every_gap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _db(tmp_path)
    feed = _Feed()
    monkeypatch.setattr(httpx, "Client", _unexpected_client)
    try:
        assert backfill(c, days_back=2, today="2026-07-25", client=feed) == 3
        assert feed.asked == ["25/07/2026", "24/07/2026", "23/07/2026"]
    finally:
        c.close()


def test_backfill_covers_a_month_by_default(tmp_path: Path) -> None:
    c = _db(tmp_path)
    feed = _Feed()
    try:
        assert backfill(c, today="2026-07-25", client=feed) == 31
    finally:
        c.close()


def test_backfill_stops_at_the_first_network_failure(tmp_path: Path) -> None:
    c = _db(tmp_path)
    feed = _Feed(fail=True)
    try:
        assert backfill(c, days_back=5, today="2026-07-25", client=feed) == 0
        assert c.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0] == 0
    finally:
        c.close()


def test_fetch_cbr_opens_its_own_client_when_not_given_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Open and close an HTTP client when the caller supplies none."""
    closed = []
    opened = []

    class _Client:
        def __init__(self, timeout: float | None = None) -> None:
            self.timeout = timeout
            self.feed = _Feed()
            opened.append(self)

        def __enter__(self) -> _Feed:
            return self.feed

        def __exit__(
            self,
            _kind: type[BaseException] | None,
            _error: BaseException | None,
            _traceback: TracebackType | None,
        ) -> bool:
            closed.append(True)
            return False

    monkeypatch.setattr(httpx, "Client", _Client)
    assert fetch_cbr("2025-07-01T09:00:00")[1]["USD"] == 78.5
    assert closed == [True]
    assert opened[0].timeout == CBR_TIMEOUT

    assert opened[0].feed.asked == ["01/07/2025"]


def test_rate_table_skips_a_currency_nothing_quotes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omit unquoted currencies while retaining the remaining table entries."""
    c = _db(tmp_path)
    monkeypatch.delitem(BUNDLED_RATES, "GEL")
    try:
        codes = [r["code"] for r in rate_table(c, "2026-07-01")]
        assert "GEL" not in codes

        assert {"AMD", "TRY", "RSD"} <= set(codes)
    finally:
        c.close()


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_store_rates_rejects_nonfinite_values(tmp_path: Path, value: float) -> None:
    c = _db(tmp_path)
    try:
        store_rates(c, "2026-01-01", {"USD": 90.0}, SOURCE_MANUAL)
        assert store_rates(c, "2026-01-01", {"USD": value}, SOURCE_MANUAL) == 0
        assert rate_on(c, "USD", "2026-01-01")[0] == 90.0
    finally:
        c.close()


@pytest.mark.parametrize(
    ("date_attribute", "requested"),
    [
        ("", "2025-07-06"),
        ('Date="32.07.2025"', "2025-07-06"),
        ('Date="07.07.2025"', "2025-07-06"),
    ],
)
def test_refresh_rejects_unusable_publication_dates(
    tmp_path: Path, date_attribute: str, requested: str
) -> None:
    c = _db(tmp_path)
    feed = _Feed(FEED.replace('Date="01.07.2025"', date_attribute))
    try:
        with pytest.raises(httpx.DecodingError):
            refresh(c, requested, client=feed)
        assert c.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0] == 0
    finally:
        c.close()


def test_weekend_refresh_preserves_manual_publication_override(tmp_path: Path) -> None:
    c = _db(tmp_path)
    try:
        store_rates(c, "2025-07-01", {"USD": 80.0}, SOURCE_MANUAL)
        refresh(c, "2025-07-06", client=_Feed())
        assert rate_on(c, "USD", "2025-07-06") == (80.0, "2025-07-01", SOURCE_MANUAL)
        assert (
            c.execute("SELECT COUNT(*) FROM exchange_rates WHERE day='2025-07-06'").fetchone()[0]
            == 0
        )
        with pytest.raises(RateUnavailableError):
            rate_on(c, "USD", "2025-06-30")
    finally:
        c.close()


@pytest.mark.parametrize(
    ("rate", "amount", "expected"),
    [(1.005, 300, 302), (1.005, -300, -302), (1.0049, 300, 301), (1.0051, 300, 302)],
)
def test_convert_rounds_decimal_quotes_without_binary_float_drift(
    tmp_path: Path, rate: float, amount: int, expected: int
) -> None:
    c = _db(tmp_path)
    try:
        store_rates(c, "2026-01-01", {"USD": rate})
        assert convert(c, amount, "USD", "RUB", "2026-01-01") == expected
    finally:
        c.close()


def test_parse_cbr_divides_decimal_quote_before_float_storage() -> None:
    payload = "<Valute><CharCode>USD</CharCode><Nominal>10</Nominal><Value>1,005</Value></Valute>"
    assert parse_cbr(payload)["USD"] == 0.1005
