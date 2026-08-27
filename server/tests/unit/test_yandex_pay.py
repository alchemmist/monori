from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from monori.common import JsonValue
from monori.server.app.connectors.base import ConnectorError, PublicConnectorError
from monori.server.app.connectors.tbank_playwright import (
    PlaywrightTimeoutError,
    TBankPlaywrightConnector,
    _PageAdapter,
)
from monori.server.app.connectors.yandex_pay import (
    YandexPayConnector,
    history_years,
    parse_amount,
    parse_date,
    parse_payment_item,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class Locator:
    def __init__(self, *, present: bool = False, frame: "Frame | None" = None) -> None:
        self.present = present
        self.frame = frame
        self.filled: str | None = None
        self.clicked = False
        self.on_click: Callable[[], None] | None = None

    @property
    def first(self) -> "Locator":
        return self

    def nth(self, _index: int) -> "Locator":
        return self

    def count(self) -> int:
        return int(self.present)

    def click(self, *, timeout: int | None = None) -> None:
        assert timeout is not None
        if not self.present:
            raise PlaywrightTimeoutError
        self.clicked = True
        if self.on_click is not None:
            self.on_click()

    def fill(self, value: str, *, timeout: int | None = None) -> None:
        assert timeout is not None
        self.filled = value

    @property
    def content_frame(self) -> "Frame":
        assert self.frame is not None
        return self.frame


class Frame:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def locator(self, selector: str) -> Locator:
        return Locator(
            present=(
                (self.mode == "phone" and "tel" in selector)
                or (self.mode == "password" and "password" in selector)
                or (self.mode == "code" and "inputmode" in selector)
            )
        )


class Page:
    def __init__(
        self,
        mode: str = "logged",
        *,
        payload: list[dict[str, JsonValue]] | None = None,
        filter_active: bool = True,
    ) -> None:
        self.mode = mode
        self.payload = (
            [{"titles": ["Merchant"], "amount": "-100 ₽", "date": "August 23"}]
            if payload is None
            else payload
        )
        self.filter_active = filter_active
        self.goto_calls = 0
        self.url = (
            "https://bank.yandex.ru/my/history"
            if mode == "logged"
            else "https://bank.yandex.ru/_pay/login"
        )
        self.keyboard = type(
            "Keyboard", (), {"press": lambda *_args: None, "type": lambda *_args: None}
        )()
        self.counts = [1, 1]

    def goto(self, url: str, *, wait_until: str | None = None) -> None:
        del wait_until
        self.goto_calls += 1
        self.url = (
            "https://bank.yandex.ru/_pay/login"
            if self.mode == "retry" and self.goto_calls == 1
            else url
        )

    def wait_for_timeout(self, _timeout: int) -> None:
        return

    def query_selector(self, selector: str) -> str | None:
        return "main" if selector == "main" and self.mode == "logged" else None

    def locator(self, selector: str) -> Locator:
        if selector == "iframe":
            return Locator(
                present=self.mode in {"phone", "password", "code", "chooser"},
                frame=Frame(self.mode),
            )
        if selector == "main a[aria-haspopup='true']":
            return Locator(present=True)
        return Locator()

    def get_by_text(self, text: str, *, exact: bool = False) -> Locator:
        locator = Locator(
            present=(
                (self.mode == "chooser" and exact and text == "Get code via push")
                or (
                    self.mode == "chooser_ru"
                    and exact
                    and text == "Получить код по \u0421\u041c\u0421"
                )
                or (self.mode == "filter" and exact and text == "Pay card")
            )
        )
        if self.mode == "filter":
            locator.on_click = lambda: setattr(self, "filter_active", True)
        return locator

    def evaluate(self, expression: str) -> JsonValue:
        if "some(button" in expression:
            return self.filter_active
        if "window.scrollTo" in expression:
            return None
        return self.payload


def test_parse_amount() -> None:
    assert parse_amount("\N{MINUS SIGN}1 234,50 ₽") == -123450
    assert parse_amount("+99,9 ₽") == 9990
    assert parse_amount("1 ₽") == 100
    assert parse_amount("1,2 ₽") == 120
    assert parse_amount("-0,5 ₽") == -50
    assert parse_amount("\N{MINUS SIGN}1\u00a0234,50 ₽") == -123450
    with pytest.raises(ConnectorError, match="amount is missing"):
        parse_amount("not an amount")


class ConnectorWithCode(YandexPayConnector):
    def ask_sms(self, _message: str = "") -> str:
        return "123456"


def test_parse_date() -> None:
    assert parse_date("25 августа 2026", year=2020) == "2026-08-25T00:00:00"
    assert parse_date("авг. •• 2026", year=2020) == "2026-08-01T00:00:00"
    assert parse_date("August 23", year=2026) == "2026-08-23T00:00:00"
    now = datetime.now(UTC).date()
    assert parse_date("today", year=2026) == f"{now.isoformat()}T00:00:00"
    assert parse_date("yesterday", year=2026) == f"{(now - timedelta(days=1)).isoformat()}T00:00:00"
    assert parse_date("сегодня", year=2026).startswith(f"{now.year}-")
    assert parse_date("вчера", year=2026).startswith(f"{now.year}-")
    with pytest.raises(ConnectorError, match="date is missing"):
        parse_date("not a date", year=2026)


def test_history_years_handles_new_year_without_explicit_year() -> None:
    reference_year = datetime.now(UTC).year
    assert history_years(["January 2", "December 31"], year=reference_year) == [
        reference_year,
        reference_year - 1,
    ]
    assert history_years(["25 августа 2025"], year=reference_year) == [2025]
    assert history_years(["2 января", "31 декабря"], year=reference_year) == [
        reference_year,
        reference_year - 1,
    ]
    assert history_years(["today", "yesterday"], year=reference_year) == [
        reference_year,
        reference_year,
    ]
    assert history_years(["August 23, 2026", "December 31, 2025"], year=2020) == [2026, 2025]
    assert history_years(["today", "yesterday", "August 23"], year=2026) == [2026, 2026, 2026]


def test_history_years_uses_relative_year_across_new_year() -> None:
    assert history_years(
        ["Yesterday", "December 30"],
        year=2026,
        reference_date=date(2026, 1, 1),
    ) == [2025, 2025]


def test_connector_auth_steps_and_history() -> None:
    connector = ConnectorWithCode({"phone": "+70000000000", "password": "pw"})
    connector.ensure_logged_in(Page())
    assert connector.choose_code_method(Page("chooser"))
    assert connector.choose_code_method(Page("chooser_ru"))
    assert connector.drive_auth_step(Page("phone"))
    assert connector.drive_auth_step(Page("password"))
    assert connector.drive_auth_step(Page("code"))
    rows = connector.download_and_parse(Page(), None)
    assert len(rows) == 1
    assert not connector.choose_code_method(Page())
    with pytest.raises(ConnectorError, match="phone is missing"):
        YandexPayConnector({}).drive_auth_step(Page("phone"))
    with pytest.raises(ConnectorError, match="credential is missing"):
        YandexPayConnector({}).drive_auth_step(Page("password"))
    with pytest.raises(ConnectorError, match="login did not reach"):
        connector.ensure_logged_in(Page("retry"))
    with pytest.raises(PublicConnectorError, match="login did not reach"):
        connector.ensure_logged_in(Page("chooser"))


def test_connector_filter_requires_active_selection() -> None:
    page = Page()
    assert YandexPayConnector.pay_card_filter_active(page)
    YandexPayConnector.select_pay_card_filter(Page("filter", filter_active=False))
    with pytest.raises(PublicConnectorError, match="filter is unavailable"):
        YandexPayConnector.select_pay_card_filter(Page("empty", filter_active=False))


def test_tbank_playwright_adapter_and_period_selection() -> None:
    class Raw:
        def evaluate(self, expression: str) -> JsonValue:
            return expression

    assert _PageAdapter(Raw()).evaluate("probe") == "probe"

    class PeriodPage(Page):
        def __init__(self, *, qa_present: bool) -> None:
            super().__init__()
            self.qa_present = qa_present
            self.clicked: str | None = None

        def locator(self, selector: str) -> Locator:
            if selector == TBankPlaywrightConnector.SEL_PERIOD_TWO_MONTHS:
                locator = Locator(present=self.qa_present)
                locator.on_click = lambda: setattr(self, "clicked", selector)
                return locator
            return super().locator(selector)

        def get_by_text(self, text: str, *, exact: bool = False) -> Locator:
            locator = Locator(present=exact and text == "2 месяца")
            locator.on_click = lambda: setattr(self, "clicked", text)
            return locator

    qa_page = PeriodPage(qa_present=True)
    TBankPlaywrightConnector({}).select_period(qa_page)
    assert qa_page.clicked == TBankPlaywrightConnector.SEL_PERIOD_TWO_MONTHS

    fallback_page = PeriodPage(qa_present=False)
    TBankPlaywrightConnector({}).select_period(fallback_page)
    assert fallback_page.clicked == "2 месяца"


def test_connector_rejects_empty_or_incomplete_history() -> None:
    connector = YandexPayConnector({})
    with pytest.raises(ConnectorError, match="date is missing"):
        connector.download_and_parse(
            Page(payload=[{"titles": ["Merchant"], "amount": "", "date": ""}]), None
        )
    with pytest.raises(PublicConnectorError, match="no transactions"):
        connector.download_and_parse(Page(payload=[]), None)


def test_parse_payment_item() -> None:
    row = parse_payment_item(
        ["Merchant", "\N{MINUS SIGN}1 234,50 ₽"], ["25 августа 2026"], year=2026
    )
    assert row.date == "2026-08-25T00:00:00"
    assert row.amount == -123450
    assert row.description == "Merchant"
    assert row.bank_category == ""
    assert row.mcc == ""
    assert row.card == ""


def test_parse_payment_item_rejects_missing_fields() -> None:
    with pytest.raises(ConnectorError, match="unexpected structure"):
        parse_payment_item(["Merchant"], ["25 августа 2026"], year=2026)
