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

import base64
import contextlib
import importlib
import io
import os
import pathlib
import queue
import shutil
import tarfile
import tempfile
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import timedelta
from types import TracebackType
from typing import ClassVar, Literal, Protocol, Self, override, runtime_checkable
from urllib.parse import quote

from monori.common import JsonObject, JsonValue
from monori.server.app.connectors.base import (
    Connector,
    ConnectorError,
    ConnectorParam,
    SmsRequiredError,
    SyncResult,
    SyncRow,
    register,
)
from monori.server.app.importer import parse_statement


class _MissingPlaywrightTimeoutError(Exception): ...


class _BrowserContext(Protocol):
    @property
    def pages(self) -> list["_RawPage"]: ...

    def new_page(self) -> "_RawPage": ...

    def close(self) -> None: ...


class _Chromium(Protocol):
    def launch_persistent_context(
        self,
        user_data_dir: str,
        *,
        headless: bool,
        user_agent: str,
        accept_downloads: bool,
        args: list[str],
    ) -> _BrowserContext: ...


class _Playwright(Protocol):
    @property
    def chromium(self) -> _Chromium: ...


class _PlaywrightContextManager(Protocol):
    def __enter__(self) -> _Playwright: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


@dataclass(slots=True)
class _LoginState:
    quick_code: JsonValue | None
    tried_quick: bool = False
    otp_prompt: str = "enter the code sent by the bank"


@runtime_checkable
class _SyncPlaywright(Protocol):
    def __call__(self) -> _PlaywrightContextManager: ...


PlaywrightTimeoutError: type[Exception]

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
    PlaywrightTimeoutError = _MissingPlaywrightTimeoutError


def _load_sync_playwright() -> _SyncPlaywright:
    try:
        module = importlib.import_module("playwright.sync_api")
    except ImportError as error:
        msg = (
            "playwright is not installed; run "
            "`uv sync --group test` and `playwright install chromium`"
        )
        raise ConnectorError(msg) from error
    factory = getattr(module, "sync_playwright", None)
    if not isinstance(factory, _SyncPlaywright):
        msg = "playwright.sync_api does not provide sync_playwright"
        raise ConnectorError(msg)
    return factory


__all__ = ["PlaywrightTimeoutError", "TBankPlaywrightConnector"]


class _Locator(Protocol):
    @property
    def first(self) -> Self: ...

    def click(self, *, timeout: int | None = None) -> None: ...


class _Keyboard(Protocol):
    def type(self, text: str) -> None: ...


class _Element(Protocol):
    def inner_text(self) -> str: ...


class _Download(Protocol):
    def save_as(self, path: str) -> None: ...


class _DownloadExpectation(AbstractContextManager["_DownloadExpectation"], Protocol):
    @property
    def value(self) -> _Download: ...


class _DownloadEvent(Protocol):
    @property
    def value(self) -> _Download: ...


class _DownloadEventContext(Protocol):
    def __enter__(self) -> _DownloadEvent: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


class _LocatorPage(Protocol):
    def locator(self, selector: str) -> _Locator: ...


type _WaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]
type _LoadState = Literal["domcontentloaded", "load", "networkidle"]


class _Page(_LocatorPage, Protocol):
    @property
    def url(self) -> str: ...

    @property
    def keyboard(self) -> _Keyboard: ...

    def set_default_navigation_timeout(self, timeout: int) -> None: ...

    def set_default_timeout(self, timeout: int) -> None: ...

    def goto(self, url: str, *, wait_until: _WaitUntil | None = None) -> None: ...

    def wait_for_timeout(self, timeout: int) -> None: ...

    def wait_for_load_state(self, state: _LoadState, *, timeout: int | None = None) -> None: ...

    def fill(self, selector: str, value: str) -> None: ...

    def query_selector(self, selector: str) -> _Element | None: ...

    def get_by_text(self, text: str, *, exact: bool = False) -> _Locator: ...

    def expect_download(self, *, timeout: int | None = None) -> _DownloadExpectation: ...

    def screenshot(self, *, path: str, full_page: bool = False) -> bytes: ...

    def content(self) -> str: ...


class _NavigationResponse(Protocol):
    pass


class _RawPage(_LocatorPage, Protocol):
    @property
    def url(self) -> str: ...

    @property
    def keyboard(self) -> _Keyboard: ...

    def set_default_navigation_timeout(self, timeout: float) -> None: ...

    def set_default_timeout(self, timeout: float) -> None: ...

    def goto(
        self,
        url: str,
        *,
        timeout: float | timedelta | None = None,
        wait_until: _WaitUntil | None = None,
        referer: str | None = None,
    ) -> _NavigationResponse | None: ...

    def wait_for_timeout(self, timeout: float) -> None: ...

    def wait_for_load_state(
        self,
        state: _LoadState = "load",
        *,
        timeout: float | timedelta | None = None,
    ) -> None: ...

    def fill(self, selector: str, value: str, *, timeout: float | None = None) -> None: ...

    def query_selector(self, selector: str) -> _Element | None: ...

    def get_by_text(self, text: str, *, exact: bool = False) -> _Locator: ...

    def expect_download(
        self,
        predicate: Callable[[_Download], bool] | None = None,
        *,
        timeout: float | timedelta | None = None,
    ) -> _DownloadEventContext: ...

    def screenshot(self, *, path: str, full_page: bool = False) -> bytes: ...

    def content(self) -> str: ...


class _DownloadExpectationAdapter(AbstractContextManager["_DownloadExpectationAdapter"]):
    def __init__(self, expectation: _DownloadEventContext) -> None:
        """Initialize the instance."""
        self._expectation = expectation
        self._event: _DownloadEvent | None = None

    @override
    def __enter__(self) -> Self:
        self._event = self._expectation.__enter__()
        return self

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return self._expectation.__exit__(exc_type, exc_value, traceback)

    @property
    def value(self) -> _Download:
        if self._event is None:
            msg = "download expectation has not been entered"
            raise RuntimeError(msg)
        return self._event.value


class _PageAdapter:
    def __init__(self, page: _RawPage) -> None:
        """Initialize the instance."""
        self._page = page

    @property
    def url(self) -> str:
        return self._page.url

    @property
    def keyboard(self) -> _Keyboard:
        return self._page.keyboard

    def set_default_navigation_timeout(self, timeout: int) -> None:
        self._page.set_default_navigation_timeout(timeout)

    def set_default_timeout(self, timeout: int) -> None:
        self._page.set_default_timeout(timeout)

    def goto(self, url: str, *, wait_until: _WaitUntil | None = None) -> None:
        self._page.goto(url, wait_until=wait_until)

    def wait_for_timeout(self, timeout: int) -> None:
        self._page.wait_for_timeout(timeout)

    def wait_for_load_state(self, state: _LoadState, *, timeout: int | None = None) -> None:
        self._page.wait_for_load_state(state, timeout=timeout)

    def fill(self, selector: str, value: str) -> None:
        self._page.fill(selector, value)

    def query_selector(self, selector: str) -> _Element | None:
        return self._page.query_selector(selector)

    def get_by_text(self, text: str, *, exact: bool = False) -> _Locator:
        return self._page.get_by_text(text, exact=exact)

    def locator(self, selector: str) -> _Locator:
        return self._page.locator(selector)

    def expect_download(self, *, timeout: int | None = None) -> _DownloadExpectation:
        return _DownloadExpectationAdapter(self._page.expect_download(timeout=timeout))

    def screenshot(self, *, path: str, full_page: bool = False) -> bytes:
        return self._page.screenshot(path=path, full_page=full_page)

    def content(self) -> str:
        return self._page.content()


type _ToWorkerMessage = tuple[Literal["sms"], str] | tuple[Literal["cancel"], None]
type _FromWorkerMessage = tuple[str, SyncResult | str]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


@register
class TBankPlaywrightConnector(Connector):
    """Represent TBankPlaywrightConnector."""

    bank = "tbank"
    kind = "playwright"
    label = "T-Bank (browser sync)"
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

    EXPORT_FORMAT_LABELS = (
        "Download CSV",
        "Скачать в CSV",
        "Выгрузить в CSV",
        "CSV-файл",
        "CSV",
    )

    TITLE_SET_CODE = "Придумайте код"

    LOGIN_STEPS = 24
    STEP_PAUSE_MS = 2_500
    LOGIN_TIMEOUT_MS = 45_000

    def __init__(
        self,
        credentials: JsonObject | None,
        session: JsonObject | None = None,
        account_ref: str | None = None,
    ) -> None:
        """Initialize the instance."""
        super().__init__(credentials, session, account_ref)
        self._worker: threading.Thread | None = None
        self.to_worker: queue.Queue[_ToWorkerMessage] = queue.Queue()
        self.from_worker: queue.Queue[_FromWorkerMessage] = queue.Queue()

    @override
    def sync(self, since: str | None = None) -> SyncResult:
        """Handle sync."""
        self._worker = threading.Thread(target=self._run, args=(since,), daemon=True)
        self._worker.start()
        return self.await_worker()

    @override
    def resume_sync(self, code: str) -> SyncResult:
        """Handle resume sync."""
        if self._worker is None or not self._worker.is_alive():
            msg = "no login in progress"
            raise ConnectorError(msg)
        self.to_worker.put(("sms", code))
        return self.await_worker()

    @override
    def close(self) -> None:
        """Handle close."""
        if self._worker is not None and self._worker.is_alive():
            self.to_worker.put(("cancel", None))
            self._worker.join(timeout=10)

    def await_worker(self) -> SyncResult:
        """Wait for the next worker event and return or raise its result."""
        kind, payload = self.from_worker.get()
        if kind == "sms_required":
            raise SmsRequiredError(payload)
        if kind == "error":
            raise ConnectorError(payload)
        if kind == "result":
            if isinstance(payload, SyncResult):
                return payload
            msg = "worker returned an invalid result"
            raise ConnectorError(msg)
        if isinstance(payload, SyncResult):
            msg = "unexpected worker payload"
            raise ConnectorError(msg)
        msg = f"unexpected worker message: {kind}"
        raise ConnectorError(msg)

    def ask_sms(self, message: str = "enter the code sent by the bank") -> str:
        """Signal the router that an OTP is needed and block for the code."""
        self.from_worker.put(("sms_required", message))
        kind, code = self.to_worker.get()
        if kind != "sms":
            msg = "login aborted"
            raise ConnectorError(msg)
        if code is None:
            msg = "login aborted"
            raise ConnectorError(msg)
        return code

    def _run(self, since: str | None) -> None:
        try:
            playwright = _load_sync_playwright()
        except ConnectorError as error:
            self.from_worker.put(
                (
                    "error",
                    str(error),
                ),
            )
            return

        work_dir = tempfile.mkdtemp(prefix="tbank-profile-")
        try:
            self.restore_profile(work_dir)
            with playwright() as p:
                args = ["--disk-cache-size=1"]
                if getattr(os, "geteuid", lambda: -1)() == 0:
                    args.append("--no-sandbox")
                context = p.chromium.launch_persistent_context(
                    work_dir,
                    headless=self.headless(),
                    user_agent=USER_AGENT,
                    accept_downloads=True,
                    args=args,
                )
                raw_page = context.pages[0] if context.pages else context.new_page()
                page: _Page = _PageAdapter(raw_page)

                page.set_default_navigation_timeout(self.LOGIN_TIMEOUT_MS)
                page.set_default_timeout(self.LOGIN_TIMEOUT_MS)
                try:
                    self.ensure_logged_in(page)
                    rows = self.download_and_parse(page, since)
                except Exception:
                    self._save_debug(page)
                    raise
                finally:
                    context.close()
                session: JsonObject = {"profile": self.archive_profile(work_dir)}
                self.from_worker.put(("result", SyncResult(rows, session=session)))
        except (
            ConnectorError,
            PlaywrightTimeoutError,
            OSError,
            RuntimeError,
            ValueError,
            tarfile.TarError,
        ) as error:
            self.from_worker.put(("error", str(error)))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def restore_profile(self, work_dir: str) -> None:
        """Restore the saved browser profile into a working directory."""
        session = self.session
        blob = session.get("profile") if session else None
        if not isinstance(blob, str) or not blob:
            return
        with contextlib.suppress(Exception):
            raw = base64.b64decode(blob)
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
                tar.extractall(work_dir, filter="data")

    def archive_profile(self, work_dir: str) -> str:
        """Archive a browser profile for storage in the connector session."""
        self.prune_cache(work_dir)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(work_dir, arcname=".")
        return base64.b64encode(buf.getvalue()).decode()

    @staticmethod
    def prune_cache(work_dir: str) -> None:
        """
        Drop Chromium cache dirs before archiving so the encrypted session.

        blob stays small — only cookies/localStorage/IndexedDB matter.
        """
        junk = {
            "Cache",
            "Code Cache",
            "GPUCache",
            "GrShaderCache",
            "ShaderCache",
            "DawnCache",
            "DawnGraphiteCache",
            "component_crx_cache",
        }
        for root, dirs, _files in os.walk(work_dir):
            for d in list(dirs):
                if d in junk:
                    shutil.rmtree(pathlib.Path(root) / d, ignore_errors=True)
                    dirs.remove(d)

    @staticmethod
    def headless() -> bool:
        """Return whether connector should run in headless mode."""
        return os.environ.get("MONORI_CONNECTOR_HEADED") not in ("1", "true")

    @staticmethod
    def debug_on() -> bool:
        """Return whether connector debug mode is enabled."""
        return bool(os.environ.get("MONORI_CONNECTOR_DEBUG"))

    @classmethod
    def shot(cls, page: _Page, name: str) -> None:
        """Save a screenshot and page HTML when connector debugging is enabled."""
        if not cls.debug_on():
            return
        out = pathlib.Path("data")

        with contextlib.suppress(Exception):
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / f"tbank-{name}.png"), full_page=True)
            (out / f"tbank-{name}.html").write_text(
                f"<!-- url: {page.url} -->\n{page.content()}",
                encoding="utf-8",
            )

    def _save_debug(self, page: _Page) -> None:
        self.shot(page, "error")

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

    def ensure_logged_in(self, page: _Page) -> None:
        """Ensure authenticated session and navigate to home page when needed."""
        page.goto(self.URL_HOME, wait_until="domcontentloaded")
        page.wait_for_timeout(1_500)
        self.shot(page, "01-open")
        if self.is_logged_in(page):
            return

        on_sso = (
            page.query_selector(self.SEL_PHONE)
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
        self._raise_if_access_denied(page)
        if page.query_selector(self.SEL_PHONE):
            self._fill_credential(page, self.SEL_PHONE, "phone")
        elif page.query_selector(self.SEL_PASSWORD):
            self._fill_credential(page, self.SEL_PASSWORD, "password")
        elif page.query_selector(self.SEL_OTP):
            self._submit_otp(page, state)
        elif page.query_selector(self.SEL_PIN):
            self._submit_pin(page, state)
        else:
            self._return_to_home(page)

    def _raise_if_access_denied(self, page: _Page) -> None:
        if blocked := self._access_denied(page):
            msg = f"the bank blocked the login: {blocked}"
            raise ConnectorError(msg)

    def _fill_credential(self, page: _Page, selector: str, name: str) -> None:
        value = self.credentials.get(name)
        if not isinstance(value, str):
            msg = f"missing {name}"
            raise ConnectorError(msg)
        page.fill(selector, value)
        self.submit(page)

    def _submit_otp(self, page: _Page, state: _LoginState) -> None:
        page.fill(self.SEL_OTP, self.ask_sms(state.otp_prompt))
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

    def download_and_parse(self, page: _Page, _since: str | None) -> list[SyncRow]:
        """Download a CSV statement from operations and parse it to sync rows."""
        page.goto(self.operations_url(), wait_until="domcontentloaded")

        with contextlib.suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=self.LOGIN_TIMEOUT_MS)
        page.wait_for_timeout(2_500)
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
            text = pathlib.Path(tmp.name).read_text(encoding="utf-8", errors="replace")
        rows, _ = parse_statement(text)
        return [row.to_sync_dict() for row in rows]

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
