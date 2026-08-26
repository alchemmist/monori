"""Yandex Pay history connector and DOM parser."""

from __future__ import annotations

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
AMOUNT_RE = re.compile(r"([+\-\N{MINUS SIGN}]?\s*[0-9][0-9\u00a0 ]*(?:[,.][0-9]{1,2})?)")
DATE_RE = re.compile(r"(\d{1,2})\s+([\u0410-\u042f\u0430-\u044fЁё]+)(?:\s+(\d{4}))?")
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
    if normalized == "сегодня":
        result = today
    elif normalized == "вчера":
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
            month_year = MONTH_YEAR_RE.search(normalized)
            if month_year is None or month_year.group(1) not in MONTHS:
                raise ConnectorError(DATE_MISSING)
            result = datetime(int(month_year.group(2)), MONTHS[month_year.group(1)], 1, tzinfo=UTC)
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
    HISTORY_URL = "https://id.yandex.ru/pay/history"

    @override
    def ensure_logged_in(self, page: _Page) -> None:
        """Authenticate with Yandex ID when the saved browser session expired."""
        page.goto(self.HISTORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        for _ in range(30):
            if "/pay/history" in page.url or page.query_selector(
                "[data-testid='payments-history']"
            ):
                return
            if page.query_selector("input[type='tel'], input[name='login']"):
                phone = self.credentials.get("phone")
                if not isinstance(phone, str):
                    raise ConnectorError(PHONE_MISSING)
                selector = "input[type='tel'], input[name='login']"
                page.fill(selector, phone)
                page.keyboard.press("Enter")
            elif page.query_selector("input[type='password']"):
                password = self.credentials.get("password")
                if not isinstance(password, str):
                    raise ConnectorError(LOGIN_SECRET_MISSING)
                page.fill("input[type='password']", password)
                page.keyboard.press("Enter")
            elif page.query_selector("input[inputmode='numeric'], input[type='number']"):
                code = self.ask_sms("enter the code from the Yandex ID push notification")
                page.locator("input[inputmode='numeric'], input[type='number']").first.click(
                    timeout=5000
                )
                page.keyboard.type(code)
                page.keyboard.press("Enter")
            elif page.query_selector("[data-testid='cell']"):
                page.locator("[data-testid='cell']").first.click(timeout=5000)
            else:
                page.wait_for_timeout(1000)
            page.wait_for_timeout(1500)
        raise PublicConnectorError(LOGIN_FAILED)

    @override
    def download_and_parse(self, page: _Page, _since: str | None) -> list[SyncRow]:
        """Load all lazily rendered history items and parse their visible fields."""
        page.goto(self.HISTORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        previous = 0
        for _ in range(60):
            count = page.locator("[data-testid='payment-item']").count()
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(750)
            current = page.locator("[data-testid='payment-item']").count()
            if current == previous and current == count:
                break
            previous = current
        payload = cast(
            "list[dict[str, JsonValue]]",
            page.evaluate(
                """() => [...document.querySelectorAll('[data-testid=payment-item]')].map(item => ({
                    titles: [...item.querySelectorAll('[data-testid=heading-title]')]
                        .map(e => e.innerText),
                }))""",
            ),
        )
        year = datetime.now(UTC).year
        rows: list[SyncRow] = []
        for index, item in enumerate(payload):
            titles = [str(value) for value in cast("list[JsonValue]", item.get("titles", []))]
            page.locator("[data-testid='payment-item']").nth(index).click(timeout=5000)
            for _ in range(10):
                if (
                    page.query_selector(
                        "[data-testid='payment-details-viewer-dialog'] [data-testid='heading']"
                    )
                    is not None
                ):
                    break
                page.wait_for_timeout(150)
            detail_descriptions = cast(
                "list[JsonValue]",
                page.evaluate(
                    """() => [...document.querySelectorAll(
                        '[data-testid=payment-details-viewer-dialog] '
                        + '[data-testid=heading-description]'
                    )].map(e => e.innerText)"""
                ),
            )
            page.evaluate(
                """() => document.querySelector(
                    '[data-testid=payment-details-viewer-dialog] [data-testid=close]'
                )?.click()"""
            )
            page.wait_for_timeout(150)
            date_text = next(
                (str(value) for value in detail_descriptions if re.search(r"\d{4}", str(value))),
                None,
            )
            if date_text is None:
                raise ConnectorError(DATE_MISSING)
            descriptions = [date_text]
            rows.append(parse_payment_item(titles, descriptions, year=year))
        if not rows:
            raise PublicConnectorError(NO_TRANSACTIONS)
        return rows
