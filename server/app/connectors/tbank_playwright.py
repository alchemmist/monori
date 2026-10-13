"""
T-Bank connector that drives the real web cabinet with Playwright.

This logs into ``www.tbank.ru`` **as you**, downloads the operations export, and
feeds it through the same statement parser as the manual paste import. It talks
to no undocumented JSON API — it clicks the same buttons a person clicks.

To avoid an SMS on every sync it uses a **persistent browser profile** (a
directory kept next to the database): cookies and the "this browser is trusted"
device identity survive between syncs, so as long as the session stays valid no
login is needed at all. When the session does expire, the connector logs in with
a **quick-login code** it set on the bank's "create a code" screen right after
the first OTP and remembered (encrypted) in the connection's credentials — only
a brand-new device needs a fresh phone + SMS.

Reality notes (read before relying on it):

* This is automated access to your own account. It is a grey area against the
  bank's terms of service; use it on your own account at your own risk.
* **The selectors/URLs below are best-effort.** The live cabinet's markup is not
  something this code can verify; expect to adjust ``SEL_*``/``URL_*`` against
  the real site. Set ``MONORI_CONNECTOR_DEBUG=1`` to dump a screenshot + HTML at
  every step (``tbank-01-open.png`` …) so the flow can be followed and tuned.

Requires the connector dependencies installed by ``uv sync --group test``.
followed by ``playwright install chromium``.
"""

import contextlib
import csv
import pathlib
import tempfile
from collections import Counter
from dataclasses import dataclass
from typing import ClassVar, override
from urllib.parse import quote

from monori.common import JsonValue
from monori.server.app.connectors.base import (
    ConnectorChallenge,
    ConnectorError,
    ConnectorParam,
    PublicConnectorError,
    SyncRow,
    register,
)
from monori.server.app.connectors.playwright import (
    Page as _Page,
)
from monori.server.app.connectors.playwright import (
    PlaywrightConnector,
    PlaywrightTimeoutError,
)
from monori.server.app.importer import parse_statement


@dataclass(slots=True)
class _LoginState:
    quick_code: JsonValue | None
    tried_quick: bool = False
    otp_prompt: str = "enter the code sent by the bank"


type _LocatorPage = _Page

LOGIN_EXPIRED = "The TBank login session expired or rejected the code. Start bank sync again."
STATEMENT_INVALID = "The TBank statement could not be parsed. The export format may have changed."
STATEMENT_EMPTY = "TBank returned an empty statement. Check the selected account and export period."


def decode_statement(raw: bytes) -> str:
    """Decode a bank statement without masking an encoding mismatch."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:256]:
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251")


def statement_header(text: str) -> tuple[str, ...]:
    """Return normalized statement columns when the first row looks like a header."""
    first = next((line for line in text.splitlines() if line.strip()), "")
    delim = "\t" if "\t" in first else ";" if ";" in first else ","
    fields = tuple(" ".join(field.split()) for field in next(csv.reader([first], delimiter=delim)))
    lowered = " ".join(fields).lower()
    markers = ("date", "дата", "operation", "операц")
    return fields if any(marker in lowered for marker in markers) else ()


@register
class TBankPlaywrightConnector(PlaywrightConnector):
    """Represent TBankPlaywrightConnector."""

    bank = "tbank"
    kind = "playwright"
    label = "T-Bank (browser sync)"
    debug_name = "tbank"
    connection_params: ClassVar[list[ConnectorParam]] = [
        ConnectorParam(name="phone", label="Phone", required=True),
        ConnectorParam(name="password", label="Password", secret=True, required=True),
    ]
    account_params: ClassVar[list[ConnectorParam]] = [
        ConnectorParam(
            name="account",
            label="T-Bank account number",
            required=True,
            help="The number from the account's operations link in the cabinet"
            " (/mybank/operations/?account=<id>); the sync pulls exactly that"
            " account.",
        ),
    ]

    URL_LOGIN = "https://www.tbank.ru/auth/login/"
    URL_HOME = "https://www.tbank.ru/mybank/"
    URL_OPERATIONS = "https://www.tbank.ru/mybank/operations/"

    SEL_PHONE = "[automation-id='phone-input']"
    SEL_PASSWORD = "[automation-id='password-input']"  # noqa: S105

    SEL_OTP = "[automation-id='otp-input']"
    SEL_PIN = "[automation-id='pin-code-input-0']"
    SEL_SUBMIT = "[automation-id='button-submit']"
    SEL_FORM_TITLE = "[automation-id='form-title']"

    SEL_ACCESS_DENIED = "[automation-id='access-denied-popup']"
    SEL_ACCESS_DENIED_TITLE = "[automation-id='access-denied-title']"
    SEL_ACCESS_DENIED_DESC = "[automation-id='access-denied-description']"

    SEL_EXPORT_TRIGGER = "[data-qa-type='molecule-export-dropdown-operations-button']"
    SEL_EXPORT_CSV = "[data-qa-type~='molecule-export-dropdown-operations-menuItem-csv']"
    SEL_PERIOD_TWO_MONTHS = "[data-qa-type='period-tab-2 месяца']"

    EXPORT_FORMAT_LABELS = (
        "Download CSV",
        "Скачать в CSV",
        "Выгрузить в CSV",
        "CSV-файл",
        "CSV",
    )
    PERIOD_LABELS = ("За 2 месяца", "2 месяца", "Последние 2 месяца", "60 дней")

    TITLE_SET_CODE = "Придумайте код"

    LOGIN_STEPS = 24
    STEP_PAUSE_MS = 2_500
    LOGIN_TIMEOUT_MS = 45_000

    def is_logged_in(self, page: _Page) -> bool:
        """Return True when current page appears to be a logged-in bank state."""
        if "/mybank" not in page.url:
            return False
        return not (
            page.query_selector(self.SEL_PHONE)
            or page.query_selector(self.SEL_PASSWORD)
            or page.query_selector(self.SEL_OTP)
            or page.query_selector(self.SEL_PIN)
        )

    def _access_denied(self, page: _Page) -> str:
        """
        Handle The bank's "Доступ заблокирован" popup text when it's shown, else ''.

        It blocks the phone screen (anti-automation / rate limit), so the driver
        checks for it first and fails fast with the bank's own wording.
        """
        with contextlib.suppress(Exception):
            if page.query_selector(self.SEL_ACCESS_DENIED) is None:
                return ""
            parts = []
            for sel in (self.SEL_ACCESS_DENIED_TITLE, self.SEL_ACCESS_DENIED_DESC):
                el = page.query_selector(sel)
                if el is not None:
                    text = " ".join((el.inner_text() or "").split())
                    if text:
                        parts.append(text)
            return " — ".join(parts) or "access denied"
        return ""

    def form_title(self, page: _Page) -> str:
        """Handle The heading of the current SSO step, or '' when none is shown."""
        with contextlib.suppress(Exception):
            el = page.query_selector(self.SEL_FORM_TITLE)
            if el is not None:
                return (el.inner_text() or "").strip()
        return ""

    def submit(self, page: _LocatorPage) -> None:
        """
        Click the step's submit button. Some layouts auto-advance as the last.

        digit lands, so a genuinely-absent button times out and is skipped — but.
        a real click failure (detached node, intercepted click) still surfaces.
        """
        with contextlib.suppress(PlaywrightTimeoutError):
            page.locator(self.SEL_SUBMIT).first.click(timeout=5_000)

    def _type_pin(self, page: _Page, digits: str) -> None:
        """
        Type into the 4-box pin widget used for both the SMS code and the.

        quick-login code. Focusing the first box and typing lets it auto-advance.
        across the boxes.
        """
        with contextlib.suppress(Exception):
            page.locator(self.SEL_PIN).first.click(timeout=5_000)
        page.keyboard.type(digits)
        page.wait_for_timeout(1_000)

    def _dismiss_interstitials(self, page: _Page) -> None:
        for label in ("Не сейчас", "Пропустить", "Позже", "Закрыть"):
            with contextlib.suppress(Exception):
                page.locator(f"text={label}").first.click(timeout=3_000)
                page.wait_for_timeout(1_000)

    @override
    def ensure_logged_in(self, page: _Page) -> None:
        """Ensure authenticated session and navigate to home page when needed."""
        page.goto(self.URL_HOME, wait_until="domcontentloaded")
        page.wait_for_timeout(1_500)
        self.shot(page, "01-open")
        if self.is_logged_in(page):
            return

        on_sso = (
            "/auth/" in page.url
            or page.query_selector(self.SEL_PHONE)
            or page.query_selector(self.SEL_PASSWORD)
            or page.query_selector(self.SEL_OTP)
            or page.query_selector(self.SEL_PIN)
        )
        if not on_sso:
            page.goto(self.URL_LOGIN, wait_until="domcontentloaded")
            page.wait_for_timeout(1_500)
        self.shot(page, "02-login")
        self._drive_sso_login(page)
        self.shot(page, "09-logged-in")
        if not self.is_logged_in(page):
            where = self.form_title(page) or page.url or "unknown screen"
            msg = f"login did not reach the bank home page (stuck on: {where})"
            raise ConnectorError(msg)

    def _drive_sso_login(self, page: _Page) -> None:
        """
        Walk the id.tbank.ru SSO one step at a time until we reach /mybank.

        Each iteration reacts to whatever step is on screen — phone, password, or
        the pin widget (set-a-code / enter-a-code) — so a slow render or a
        reordered step just means another pass, never a skipped field.
        """
        state = _LoginState(self.credentials.get("code"))
        for step in range(self.LOGIN_STEPS):
            if self.is_logged_in(page):
                return
            self._drive_sso_step(page, state)
            page.wait_for_timeout(self.STEP_PAUSE_MS)
            self.shot(page, f"step-{step:02d}")

    def _drive_sso_step(self, page: _Page, state: _LoginState) -> None:
        self._raise_if_auth_error(page)
        self._raise_if_access_denied(page)
        if page.query_selector(self.SEL_PHONE):
            self._fill_credential(page, self.SEL_PHONE, "phone")
        elif page.query_selector(self.SEL_PASSWORD):
            self._fill_credential(page, self.SEL_PASSWORD, "password")
        elif page.query_selector(self.SEL_OTP):
            self._submit_otp(page, state)
        elif page.query_selector(self.SEL_PIN):
            self._submit_pin(page, state)
        elif "/auth/" not in page.url:
            self._return_to_home(page)

    def _raise_if_access_denied(self, page: _Page) -> None:
        if blocked := self._access_denied(page):
            msg = f"the bank blocked the login: {blocked}"
            raise ConnectorError(msg)

    @staticmethod
    def _raise_if_auth_error(page: _Page) -> None:
        if "/auth/error" in page.url:
            raise PublicConnectorError(LOGIN_EXPIRED)

    def _fill_credential(self, page: _Page, selector: str, name: str) -> None:
        value = self.credentials.get(name)
        if not isinstance(value, str):
            msg = f"missing {name}"
            raise ConnectorError(msg)
        page.fill(selector, value)
        self.submit(page)

    def _submit_otp(self, page: _Page, state: _LoginState) -> None:
        code = self.ask_sms(
            ConnectorChallenge(kind="code", prompt=state.otp_prompt, can_resend=True)
        )
        self._raise_if_auth_error(page)
        page.fill(self.SEL_OTP, code)
        state.otp_prompt = "the bank rejected the code — check it and try again"
        self.submit(page)

    def _submit_pin(self, page: _Page, state: _LoginState) -> None:
        if self.TITLE_SET_CODE in self.form_title(page):
            self._enter_quick_code(page, state)
        elif state.quick_code and not state.tried_quick:
            self._enter_quick_code(page, state)
            state.tried_quick = True
        else:
            self._return_to_home(page)

    def _enter_quick_code(self, page: _Page, state: _LoginState) -> None:
        if not isinstance(state.quick_code, str):
            msg = "missing quick-login code"
            raise ConnectorError(msg)
        self._type_pin(page, state.quick_code)
        self.submit(page)

    def _return_to_home(self, page: _Page) -> None:
        self._dismiss_interstitials(page)
        page.goto(self.URL_HOME, wait_until="domcontentloaded")

    def operations_url(self) -> str:
        """Return operations URL optionally scoped to configured bank account."""
        account = self.account_ref or (self.credentials or {}).get("account")

        account = str(account).strip() if account is not None else ""
        if account:
            return f"{self.URL_OPERATIONS}?account={quote(account, safe='')}"
        return self.URL_OPERATIONS

    @override
    def download_and_parse(self, page: _Page, _since: str | None) -> list[SyncRow]:
        """Download a CSV statement from operations and parse it to sync rows."""
        page.goto(self.operations_url(), wait_until="domcontentloaded")

        with contextlib.suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=self.LOGIN_TIMEOUT_MS)
        page.wait_for_timeout(2_500)
        self.select_period(page)
        self.shot(page, "08-operations")

        page.locator(self.SEL_EXPORT_TRIGGER).first.click(timeout=self.LOGIN_TIMEOUT_MS)
        page.wait_for_timeout(1_000)
        self.shot(page, "09-export-menu")
        with page.expect_download(timeout=self.LOGIN_TIMEOUT_MS) as dl:
            if not self.click_export_format(page):
                msg = "could not find a CSV export option in the dropdown"
                raise ConnectorError(msg)
        download = dl.value

        with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
            download.save_as(tmp.name)
            text = decode_statement(pathlib.Path(tmp.name).read_bytes())
        rows, errors = parse_statement(text)
        if errors:
            reasons = ", ".join(
                f"{reason}: {count}" for reason, count in Counter(e.error for e in errors).items()
            )
            header = statement_header(text)
            columns = f" Columns: {' | '.join(header)}." if header else ""
            message = f"{STATEMENT_INVALID} Invalid rows: {len(errors)} ({reasons}).{columns}"
            raise PublicConnectorError(message)
        if not rows:
            raise PublicConnectorError(STATEMENT_EMPTY)
        return [row.to_sync_dict() for row in rows]

    def select_period(self, page: _Page) -> None:
        """
        Select a two-month operation window when the cabinet exposes it.
        """
        with contextlib.suppress(Exception):
            page.locator(self.SEL_PERIOD_TWO_MONTHS).first.click(timeout=5_000)
            page.wait_for_timeout(1_000)
            return
        for label in self.PERIOD_LABELS:
            with contextlib.suppress(Exception):
                page.get_by_text(label, exact=True).first.click(timeout=2_500)
                page.wait_for_timeout(1_000)
                return

    def click_export_format(self, page: _Page) -> bool:
        """Try to choose CSV export in dropdown and report whether it was found."""
        with contextlib.suppress(Exception):
            page.locator(self.SEL_EXPORT_CSV).first.click(timeout=5_000)
            return True
        for label in self.EXPORT_FORMAT_LABELS:
            with contextlib.suppress(Exception):
                page.get_by_text(label, exact=False).first.click(timeout=2_500)
                return True
        return False
