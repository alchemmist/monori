"""Yandex Pay history connector and DOM parser."""

from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar, cast, override

from monori.server.app.connectors.base import (
    ConnectorError,
    ConnectorParam,
    PublicConnectorError,
    SyncRow,
    register,
)
from monori.server.app.connectors.tbank_playwright import TBankPlaywrightConnector, _Page

if TYPE_CHECKING:
    from monori.common import JsonValue

MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
    "янв.": 1,
    "февр.": 2,
    "мар.": 3,
    "апр.": 4,
    "июн.": 6,
    "июл.": 7,
    "авг.": 8,
    "сент.": 9,
    "окт.": 10,
    "нояб.": 11,
    "дек.": 12,
}
MONTHS.update(
    {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
)
AMOUNT_RE = re.compile(r"([+\-\N{MINUS SIGN}]?\s*[0-9][0-9\u00a0 ]*(?:[,.][0-9]{1,2})?)")
DATE_RE = re.compile(r"(\d{1,2})\s+([\u0410-\u042f\u0430-\u044fЁё]+)(?:\s+(\d{4}))?")
EN_DATE_RE = re.compile(r"([A-Za-z]+)\s+(\d{1,2})(?:,\s*(\d{4}))?")
MONTH_YEAR_RE = re.compile(r"([\u0410-\u042f\u0430-\u044fЁё.]+)\s*[•.\s]+(\d{4})")
AMOUNT_MISSING = "Yandex Pay transaction amount is missing"
DATE_MISSING = "Yandex Pay transaction date is missing"
ITEM_INVALID = "Yandex Pay transaction item has an unexpected structure"
PHONE_MISSING = "Yandex Pay phone is missing"
LOGIN_SECRET_MISSING = "Yandex Pay password is missing"  # noqa: S105
LOGIN_FAILED = "Yandex ID login did not reach payment history"
NO_TRANSACTIONS = "Yandex Pay returned no transactions"
MIN_TITLES = 2


def parse_amount(value: str) -> int:
    """Parse a localized Yandex Pay amount into minor currency units."""
    match = AMOUNT_RE.search(value)
    if match is None:
        raise ConnectorError(AMOUNT_MISSING)
    raw = match.group(1).replace("\N{MINUS SIGN}", "-").replace("\u00a0", "").replace(" ", "")
    sign = -1 if raw.startswith("-") else 1
    raw = raw.lstrip("+-")
    whole, _, fraction = raw.replace(",", ".").partition(".")
    return sign * (int(whole) * 100 + int((fraction + "00")[:2]))


def parse_date(value: str, *, year: int) -> str:
    """Parse a localized Yandex Pay date into an ISO timestamp."""
    normalized = value.strip().lower()
    today = datetime.now(UTC)
    if normalized in {"сегодня", "today"}:
        result = today
    elif normalized in {"вчера", "yesterday"}:
        result = today - timedelta(days=1)
    else:
        match = DATE_RE.search(normalized)
        if match is not None and match.group(2) in MONTHS:
            result = datetime(
                int(match.group(3) or year),
                MONTHS[match.group(2)],
                int(match.group(1)),
                tzinfo=UTC,
            )
        else:
            english = EN_DATE_RE.search(normalized)
            if english is not None and english.group(1) in MONTHS:
                result = datetime(
                    int(english.group(3) or year),
                    MONTHS[english.group(1)],
                    int(english.group(2)),
                    tzinfo=UTC,
                )
            else:
                month_year = MONTH_YEAR_RE.search(normalized)
                if month_year is None or month_year.group(1) not in MONTHS:
                    raise ConnectorError(DATE_MISSING)
                result = datetime(
                    int(month_year.group(2)), MONTHS[month_year.group(1)], 1, tzinfo=UTC
                )
    return result.strftime("%Y-%m-%dT%H:%M:%S")


def parse_payment_item(titles: list[str], descriptions: list[str], *, year: int) -> SyncRow:
    """Convert one Yandex Pay history item into a sync row."""
    if len(titles) < MIN_TITLES or not descriptions:
        raise ConnectorError(ITEM_INVALID)
    return SyncRow(
        date=parse_date(descriptions[0], year=year),
        amount=parse_amount(titles[1]),
        description=titles[0].strip(),
        bank_category="",
        mcc="",
        card="",
    )


@register
class YandexPayConnector(TBankPlaywrightConnector):
    """Synchronize transactions from the authenticated Yandex Pay history."""

    bank = "yandex_pay"
    kind = "playwright"
    label = "Yandex Pay (browser sync)"
    connection_params: ClassVar[list[ConnectorParam]] = [
        ConnectorParam(name="phone", label="Phone", required=True),
        ConnectorParam(name="password", label="Password", secret=True, required=True),
    ]
    account_params: ClassVar[list[ConnectorParam]] = []
    HISTORY_URL = "https://bank.yandex.ru/my/history"
    PAY_CARD_FILTER_LABELS = ("Pay card", "Карта Пэй")

    @override
    def ensure_logged_in(self, page: _Page) -> None:
        """Authenticate with Yandex ID when the saved browser session expired."""
        page.goto(self.HISTORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        for _ in range(30):
            if "/my/history" in page.url and page.query_selector("main") is not None:
                return
            frame = page.locator("iframe[src*='yandex.ru/user-id']").first.content_frame
            if frame.locator("input[type='tel'], input[name='login']").count():
                phone = self.credentials.get("phone")
                if not isinstance(phone, str):
                    raise ConnectorError(PHONE_MISSING)
                selector = "input[type='tel'], input[name='login']"
                frame.locator(selector).first.fill(phone, timeout=5000)
                frame.locator(selector).first.click(timeout=5000)
                page.keyboard.press("Enter")
            elif frame.locator("input[type='password']").count():
                password = self.credentials.get("password")
                if not isinstance(password, str):
                    raise ConnectorError(LOGIN_SECRET_MISSING)
                frame.locator("input[type='password']").first.fill(password, timeout=5000)
                frame.locator("input[type='password']").first.click(timeout=5000)
                page.keyboard.press("Enter")
            elif frame.locator(
                "input[inputmode='numeric'], input[type='number'], "
                "input[autocomplete='one-time-code']"
            ).count():
                code = self.ask_sms("enter the code from the Yandex ID push notification")
                code_input = frame.locator(
                    "input[inputmode='numeric'], input[type='number'], "
                    "input[autocomplete='one-time-code']"
                ).first
                code_input.click(timeout=5000)
                page.keyboard.type(code)
                page.keyboard.press("Enter")
            else:
                page.wait_for_timeout(1000)
            page.wait_for_timeout(1500)
        raise PublicConnectorError(LOGIN_FAILED)

    @override
    def download_and_parse(self, page: _Page, _since: str | None) -> list[SyncRow]:
        """Load all lazily rendered history items and parse their visible fields."""
        page.goto(self.HISTORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        self.select_pay_card_filter(page)
        previous = 0
        for _ in range(60):
            count = page.locator("main a[aria-haspopup='true']").count()
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(750)
            current = page.locator("main a[aria-haspopup='true']").count()
            if current == previous and current == count:
                break
            previous = current
        payload = cast(
            "list[dict[str, JsonValue]]",
            page.evaluate(
                """() => {
                    const headings = [...document.querySelectorAll('main h3')];
                    return [...document.querySelectorAll(
                        'main a[aria-haspopup="true"]'
                    )].map(item => {
                        const heading = headings.filter(e =>
                            e.compareDocumentPosition(item) & Node.DOCUMENT_POSITION_FOLLOWING
                        ).at(-1);
                        const paragraphs = [...item.querySelectorAll('p')].map(e => e.innerText);
                        return {
                            titles: paragraphs.slice(0, 1),
                            amount: paragraphs.find(e => /[-+\u2212]?\\s*\\d/.test(e)) || '',
                            date: heading?.innerText || '',
                        };
                    });
                }""",
            ),
        )
        year = datetime.now(UTC).year
        rows: list[SyncRow] = []
        for item in payload:
            titles = [str(value) for value in cast("list[JsonValue]", item.get("titles", []))]
            amount = str(item.get("amount", ""))
            date_text = str(item.get("date", ""))
            if not amount or not date_text:
                raise ConnectorError(DATE_MISSING)
            titles.append(amount)
            descriptions = [date_text]
            rows.append(parse_payment_item(titles, descriptions, year=year))
        if not rows:
            raise PublicConnectorError(NO_TRANSACTIONS)
        return rows

    @staticmethod
    def select_pay_card_filter(page: _Page) -> None:
        """Limit the history view to Pay card operations."""
        for label in YandexPayConnector.PAY_CARD_FILTER_LABELS:
            with contextlib.suppress(Exception):
                page.get_by_text(label, exact=True).first.click(timeout=2_500)
                page.wait_for_timeout(750)
                return
