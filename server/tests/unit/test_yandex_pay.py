from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING

import pytest

import monori.server.app.connectors.yandex_pay as yandex_pay_module
from monori.common import JsonValue
from monori.server.app.connectors.base import ConnectorError, PublicConnectorError
from monori.server.app.connectors.tbank_playwright import (
    PlaywrightTimeoutError,
    TBankPlaywrightConnector,
    _PageAdapter,
)
from monori.server.app.connectors.yandex_pay import (
    AUTH_REJECTED,
    CAPTCHA_REFRESH,
    CODE_RESEND,
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
                or (
                    self.mode == "password"
                    and "password" in selector
                    and "aria-invalid" not in selector
                )
                or (
                    self.mode == "password_error"
                    and "current-password" in selector
                    and "aria-invalid" in selector
                )
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
            else (
                "https://passport.yandex.ru/pwl-yandex/auth/code"
                if mode == "code"
                else "https://bank.yandex.ru/_pay/login"
            )
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
                present=self.mode in {"phone", "password", "password_error", "code", "chooser"},
                frame=Frame(self.mode),
            )
        if selector == "main a[aria-haspopup='true']":
            return Locator(present=True)
        if selector == "button":
            return Locator(present=self.mode in {"suggest", "code"})
        present = (
            (selector == "input[placeholder='Enter the characters']" and self.mode == "captcha")
            or ("type='tel'" in selector and self.mode == "ypay_code" and ":not" not in selector)
            or ("one-time-code" in selector and self.mode == "ypay_code")
        )
        return Locator(present=present)

    def get_by_text(self, text: str, *, exact: bool = False) -> Locator:
        locator = Locator(
            present=(
                (self.mode == "chooser" and exact and text == "Get code via push")
                or (
                    self.mode == "chooser_ru"
                    and exact
                    and text == "Получить код по \u0421\u041c\u0421"
                )
                or (self.mode == "captcha" and exact and text == "Submit")
                or (self.mode == "captcha" and exact and text == "Another code")
                or (self.mode == "suggest" and exact and text == "person@example.com")
                or (self.mode == "filter" and exact and text == "Pay card")
            )
        )
        if self.mode == "filter":
            locator.on_click = lambda: setattr(self, "filter_active", True)
        if self.mode == "suggest":

            def select_account() -> None:
                self.mode = "logged"
                self.url = "https://bank.yandex.ru/my/history"

            locator.on_click = select_account
        return locator

    def evaluate(self, expression: str) -> JsonValue:
        if "some(button" in expression:
            return self.filter_active
        if "window.scrollTo" in expression:
            return None
        if "Captcha-img" in expression:
            return "https://ext.captcha.yandex.net/image?key=test"
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


class ConnectorWithAnswer(YandexPayConnector):
    def __init__(self, answer: str) -> None:
        super().__init__({"phone": "+70000000000", "password": "pw"})
        self.answer = answer
        self.messages: list[str] = []

    def ask_sms(self, message: str = "") -> str:
        self.messages.append(message)
        return self.answer


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


@pytest.mark.parametrize(
    ("heading", "expected"),
    [("сегодня", 2026), ("today", 2026), ("вчера", 2025), ("yesterday", 2025)],
)
def test_history_years_anchors_each_relative_heading(heading: str, expected: int) -> None:
    assert history_years([heading], year=1999, reference_date=date(2026, 1, 1)) == [expected]


def test_history_years_tracks_relative_and_unknown_boundaries() -> None:
    assert history_years(
        ["вчера", "yesterday"],
        year=1999,
        reference_date=date(2026, 1, 2),
    ) == [2026, 2026]
    assert history_years(
        ["today", "December 31"],
        year=1999,
        reference_date=date(2026, 1, 2),
    ) == [2026, 2025]
    assert history_years(["unknown", "January 1"], year=2026) == [2026, 2026]
    assert history_years(["January 1", "January 1"], year=2026) == [2026, 2026]


def test_relative_dates_use_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    class Clock:
        @staticmethod
        def now(timezone: tzinfo | None) -> datetime:
            assert timezone is UTC
            return datetime(2026, 1, 2, tzinfo=UTC)

    monkeypatch.setattr(yandex_pay_module, "datetime", Clock)
    assert parse_date("today", year=1999) == "2026-01-02T00:00:00"
    assert history_years(["today"], year=1999) == [2026]


def test_connector_auth_steps_and_history() -> None:
    connector = ConnectorWithCode(
        {"phone": "+70000000000", "password": "pw", "yandex_account": "person@example.com"}
    )
    connector.ensure_logged_in(Page())
    assert connector.choose_code_method(Page("chooser"))
    assert connector.choose_code_method(Page("chooser_ru"))
    assert YandexPayConnector.CODE_METHOD_LABELS.index("Let's do SMS instead") < (
        YandexPayConnector.CODE_METHOD_LABELS.index("Get code via push")
    )
    suggest = Page("suggest")
    suggest.url = "https://passport.yandex.ru/pwl-yandex/auth/suggest"
    assert connector.choose_suggested_account(suggest)
    assert suggest.mode == "logged"
    assert {param.name for param in connector.connection_params} == {
        "phone",
        "yandex_account",
        "password",
    }
    with pytest.raises(ConnectorError, match="account email or login"):
        ConnectorWithCode({"phone": "+70000000000", "password": "pw"}).choose_suggested_account(
            Page("suggest")
        )
    with pytest.raises(PublicConnectorError, match="requested account"):
        connector.choose_suggested_account(Page())
    assert connector.drive_auth_step(Page("phone"))
    assert connector.drive_auth_step(Page("password"))
    assert connector.drive_auth_step(Page("code"))
    pay_code = ConnectorWithAnswer("1234")
    assert pay_code.drive_auth_step(Page("ypay_code"))
    assert pay_code.messages == ["code:4:Enter the 4-digit code sent by Yandex Pay."]
    assert connector.drive_auth_step(Page("captcha"))
    rows = connector.download_and_parse(Page(), None)
    assert len(rows) == 1
    assert not connector.choose_code_method(Page())
    with pytest.raises(ConnectorError, match="phone is missing"):
        YandexPayConnector({}).drive_auth_step(Page("phone"))
    with pytest.raises(ConnectorError, match="credential is missing"):
        YandexPayConnector({}).drive_auth_step(Page("password"))
    with pytest.raises(PublicConnectorError, match=AUTH_REJECTED):
        connector.drive_auth_step(Page("password_error"))
    with pytest.raises(ConnectorError, match="login did not reach"):
        connector.ensure_logged_in(Page("retry"))
    with pytest.raises(PublicConnectorError, match="login did not reach"):
        connector.ensure_logged_in(Page("chooser"))


def test_connector_handles_suggest_resend_and_captcha_refresh() -> None:
    class SuggestPage(Page):
        def __init__(self) -> None:
            super().__init__("suggest")
            self.url = "https://passport.yandex.ru/pwl-yandex/auth/suggest"

        def goto(self, url: str, *, wait_until: str | None = None) -> None:
            del wait_until
            self.url = (
                url
                if self.mode == "logged"
                else "https://passport.yandex.ru/pwl-yandex/auth/suggest"
            )

        def locator(self, selector: str) -> Locator:
            locator = super().locator(selector)
            if selector == "button":

                def select() -> None:
                    self.mode = "logged"
                    self.url = "https://bank.yandex.ru/my/history"

                locator.on_click = select
            return locator

    ConnectorWithCode(
        {"phone": "+70000000000", "password": "pw", "yandex_account": "person@example.com"}
    ).ensure_logged_in(SuggestPage())
    assert ConnectorWithAnswer(CODE_RESEND).drive_auth_step(Page("code"))
    assert ConnectorWithAnswer(CAPTCHA_REFRESH).drive_auth_step(Page("captcha"))

    class InvalidCaptchaPage(Page):
        def evaluate(self, expression: str) -> JsonValue:
            if "Captcha-img" in expression:
                return "https://example.com/not-yandex"
            return super().evaluate(expression)

    captcha = ConnectorWithAnswer("answer")
    assert captcha.drive_auth_step(InvalidCaptchaPage("captcha"))
    assert captcha.messages == ["captcha:"]


def test_connector_waits_for_auth_dom_transition() -> None:
    class TransitionPage(Page):
        def __init__(self) -> None:
            super().__init__("phone")
            self.pending = False
            self.keyboard = type(
                "Keyboard",
                (),
                {
                    "press": lambda _keyboard, _key: setattr(self, "pending", True),
                    "type": lambda *_args: None,
                },
            )()

        def wait_for_timeout(self, _timeout: int) -> None:
            if self.pending:
                self.mode = "logged"
                self.url = YandexPayConnector.HISTORY_URL

    ConnectorWithCode({"phone": "+70000000000"}).ensure_logged_in(TransitionPage())


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
