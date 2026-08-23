"""
Unit tests for the T-Bank Playwright connector's flow logic.

The real browser is replaced by a scripted fake page/context, so the login
sequence, selectors, quick-login-code handling, statement download and the
encrypted-profile round-trip are all exercised without Chromium or the bank.
"""

import base64
import io
import pathlib
import sys
import tarfile
import threading
import types
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import ClassVar, Literal, Self, override

import pytest

from monori.common import JsonObject
from monori.server.app.connectors import tbank_playwright as tbank_mod
from monori.server.app.connectors.base import (
    ConnectorError,
    SmsRequiredError,
    SyncResult,
    get_connector_class,
)
from monori.server.app.connectors.fake import FIXTURE_ROWS, _rows
from monori.server.app.connectors.tbank_playwright import TBankPlaywrightConnector as TBankConnector

STATEMENT = (
    "05.01.2026 10:00:00\t05.01.2026\t*1\tOK\t-100,00\tRUB\t-100,00\tRUB\t\tSuper\t5411\t"
    "Lenta\t0\t0\t-100,00\n"
    "06.01.2026 11:00:00\t06.01.2026\t*1\tOK\t-200,00\tRUB\t-200,00\tRUB\t\tSuper\t5411\t"
    "Okey\t0\t0\t-200,00\n"
)

CREDS: JsonObject = {"phone": "+70000000000", "password": "pw", "code": "1234"}


@dataclass(frozen=True)
class PageEvent:
    kind: str
    argument: str | int
    value: str | None = None


class FakeLocator:
    def __init__(
        self,
        page: "FakePage",
        *,
        present: bool,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        self.page = page
        self._present = present
        self._on_click = on_click

    @property
    def first(self) -> Self:
        return self

    def count(self) -> int:
        return 1 if self._present else 0

    def click(self, timeout: int | None = None) -> None:
        if timeout is None:
            msg = "connector clicks must have a timeout"
            raise AssertionError(msg)

        if not self._present:
            msg = "locator not present"
            raise tbank_mod.PlaywrightTimeoutError(msg)
        if self._on_click:
            self._on_click()


class FakeKeyboard:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def type(self, text: str) -> None:
        self.page.log.append(PageEvent("type", text))

        self.page.last_code = text
        if self.page.stage in self.page.PIN_STAGES:
            self.page.advance()


class FakeElement:
    def __init__(self, text: str) -> None:
        self._text = text

    def inner_text(self) -> str:
        return self._text


class FakeDownload:
    def __init__(self, text: str) -> None:
        self._text = text

    def save_as(self, path: str) -> None:
        pathlib.Path(path).write_text(self._text, encoding="utf-8")


class FakeDownloadExpectation:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        return False

    @property
    def value(self) -> FakeDownload:
        if not self.page.download_triggered:
            msg = "no download happened"
            raise RuntimeError(msg)
        return FakeDownload(self.page.csv)


class FakePage:
    """
    A scripted stand-in for a Playwright page driving the id.tbank.ru SSO.

    ``stage`` is the current step: phone → password → sms → setcode → in for a
    fresh login, ``quickcode`` for a trusted-device quick login, and in/ops/
    export_open for the post-login statement download. The SMS step is a single
    ``otp-input`` (auto-submits); the 4-box pin widget backs only the
    quick-login/set-code screens.
    """

    TITLES: ClassVar[dict[str, str]] = {
        "phone": "Sign in to T-Bank",
        "password": "Enter password",
        "sms": "Enter code",
        "setcode": TBankConnector.TITLE_SET_CODE,
        "quickcode": "Enter code",
    }
    PIN_STAGES = ("setcode", "quickcode")

    def __init__(
        self,
        *,
        scenario: str = "fresh",
        export_label: str = "CSV",
        csv_hook: bool = True,
        csv: str = STATEMENT,
        wrong_codes: set[str] | None = None,
    ) -> None:
        self.scenario = scenario
        self.export_label = export_label

        self.csv_hook = csv_hook
        self.csv = csv
        self.wrong_codes = wrong_codes or set()
        self.last_code: str | None = None
        self.url = ""
        self.log: list[PageEvent] = []
        self.keyboard = FakeKeyboard(self)
        self.download_triggered = False
        self.screenshots: list[tuple[str, bool]] = []
        self.load_timeout: int | None = None
        self.download_timeout: int | None = None
        self.launch_options: tuple[str, bool, str, bool, list[str]] | None = None
        self.nav_timeout: int | None = None
        self.action_timeout: int | None = None
        self.stage = {"logged_in": "in", "quick": "quickcode"}.get(scenario, "start")

    def set_default_navigation_timeout(self, ms: int) -> None:
        self.nav_timeout = ms

    def set_default_timeout(self, ms: int) -> None:
        self.action_timeout = ms

    def goto(self, url: str, wait_until: str | None = None) -> None:
        self.log.append(PageEvent("goto", url, wait_until))
        if url == TBankConnector.URL_HOME:
            if self.scenario == "logged_in" or self.stage == "in":
                self.stage, self.url = "in", TBankConnector.URL_HOME
            elif self.scenario == "quick":
                self.stage, self.url = "quickcode", TBankConnector.URL_LOGIN
            else:
                self.stage, self.url = "phone", TBankConnector.URL_LOGIN
        elif url == TBankConnector.URL_LOGIN:
            self.stage = "quickcode" if self.scenario == "quick" else "phone"
            self.url = TBankConnector.URL_LOGIN
        elif url == TBankConnector.URL_OPERATIONS:
            self.stage, self.url = "ops", TBankConnector.URL_OPERATIONS

    def wait_for_timeout(self, ms: int) -> None:
        self.log.append(PageEvent("wait", ms))

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        self.load_timeout = timeout
        self.log.append(PageEvent("load_state", state))

    def fill(self, selector: str, value: str) -> None:
        self.log.append(PageEvent("fill", selector, value))
        if selector == TBankConnector.SEL_OTP and self.stage == "sms":
            self.last_code = value
            self.advance()

    def query_selector(self, selector: str) -> FakeElement | None:
        self.log.append(PageEvent("query", selector))
        if (
            (selector == TBankConnector.SEL_PHONE and self.stage == "phone")
            or (selector == TBankConnector.SEL_PASSWORD and self.stage == "password")
            or (selector == TBankConnector.SEL_OTP and self.stage == "sms")
            or (selector == TBankConnector.SEL_PIN and self.stage in self.PIN_STAGES)
        ):
            return FakeElement("")
        if selector == TBankConnector.SEL_FORM_TITLE and self.stage in self.TITLES:
            return FakeElement(self.TITLES[self.stage])
        return None

    def get_by_text(self, text: str, *, exact: bool = False) -> FakeLocator:
        matches_label = text == self.export_label if exact else text in self.export_label
        present = self.stage == "export_open" and not self.csv_hook and matches_label

        def on_click() -> None:
            if self.stage == "export_open":
                self.download_triggered = True

        return FakeLocator(self, present=present, on_click=on_click)

    def advance(self) -> None:
        if self.stage == "phone":
            self.stage = "password"
        elif self.stage == "password":
            self.stage = "sms"
        elif self.stage == "sms":
            self.stage = "sms" if self.last_code in self.wrong_codes else "setcode"
        elif self.stage in ("setcode", "quickcode"):
            self.stage, self.url = "in", TBankConnector.URL_HOME

    def _advance(self) -> None:
        self.advance()

    def locator(self, selector: str) -> FakeLocator:
        present = False
        on_click = None
        if selector == TBankConnector.SEL_PIN and self.stage in self.PIN_STAGES:
            present = True
        elif selector == TBankConnector.SEL_SUBMIT and self.stage in (
            *self.PIN_STAGES,
            "phone",
            "password",
        ):
            present = True

            if self.stage in ("phone", "password"):
                on_click = self.advance
        elif selector == TBankConnector.SEL_EXPORT_TRIGGER and self.stage == "ops":
            present = True

            def on_click() -> None:
                self.stage = "export_open"

        elif (
            selector == TBankConnector.SEL_EXPORT_CSV
            and self.stage == "export_open"
            and self.csv_hook
        ):
            present = True

            def on_click() -> None:
                self.download_triggered = True

        return FakeLocator(self, present=present, on_click=on_click)

    def expect_download(self, timeout: int | None = None) -> FakeDownloadExpectation:
        self.download_timeout = timeout
        return FakeDownloadExpectation(self)

    def screenshot(self, *, path: str, full_page: bool = False) -> bytes:
        self.screenshots.append((path, full_page))
        return b""

    def content(self) -> str:
        return "<html></html>"


def _connector(
    creds: JsonObject | None = None,
    session: JsonObject | None = None,
) -> TBankConnector:
    return TBankConnector(creds if creds is not None else dict(CREDS), session)


def test_headless_default_and_headed_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONORI_CONNECTOR_HEADED", raising=False)
    assert TBankConnector.headless() is True
    monkeypatch.setenv("MONORI_CONNECTOR_HEADED", "1")
    assert TBankConnector.headless() is False


def test_debug_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONORI_CONNECTOR_DEBUG", raising=False)
    assert TBankConnector.debug_on() is False
    monkeypatch.setenv("MONORI_CONNECTOR_DEBUG", "1")
    assert TBankConnector.debug_on() is True


def test_is_logged_in_is_true_only_on_mybank() -> None:
    c = _connector()
    page = FakePage(scenario="logged_in")
    page.stage, page.url = "in", TBankConnector.URL_HOME
    assert c.is_logged_in(page) is True

    page.url = TBankConnector.URL_LOGIN
    assert c.is_logged_in(page) is False


def test_is_logged_in_false_when_a_code_prompt_is_reparked_over_mybank() -> None:
    c = _connector()
    page = FakePage(scenario="fresh")

    page.stage, page.url = "setcode", TBankConnector.URL_HOME
    assert c.is_logged_in(page) is False


def test_form_title_reads_heading_or_empty() -> None:
    c = _connector()
    page = FakePage(scenario="fresh")
    page.stage = "password"
    assert c.form_title(page) == "Enter password"
    page.stage = "in"
    assert c.form_title(page) == ""


def test_click_export_format_uses_stable_hook() -> None:
    c = _connector()
    page = FakePage(csv_hook=True)
    page.stage = "export_open"
    assert c.click_export_format(page) is True
    assert page.download_triggered is True


def test_click_export_format_falls_back_to_label() -> None:
    c = _connector()

    page = FakePage(csv_hook=False, export_label="Download CSV")
    page.stage = "export_open"
    assert c.click_export_format(page) is True
    assert page.download_triggered is True


def test_click_export_format_none_present() -> None:
    c = _connector()
    page = FakePage(csv_hook=False, export_label="nope")
    page.stage = "export_open"
    assert c.click_export_format(page) is False
    assert page.download_triggered is False


def test_already_logged_in_skips_login() -> None:
    c = _connector()
    page = FakePage(scenario="logged_in")
    c.ensure_logged_in(page)

    assert not any(
        event.kind == "goto" and event.argument == TBankConnector.URL_LOGIN for event in page.log
    )
    assert not any(event.kind == "fill" for event in page.log)


def test_quick_login_uses_stored_code() -> None:
    c = _connector()
    page = FakePage(scenario="quick")
    c.ensure_logged_in(page)
    assert PageEvent("type", "1234") in page.log

    assert not any(event.kind == "fill" for event in page.log)


def test_full_login_enters_phone_password_otp_then_sets_code() -> None:
    c = _connector()
    c.to_worker.put(("sms", "9999"))
    page = FakePage(scenario="fresh")
    c.ensure_logged_in(page)
    fills = [event for event in page.log if event.kind == "fill"]
    assert PageEvent("fill", TBankConnector.SEL_PHONE, "+70000000000") in fills
    assert PageEvent("fill", TBankConnector.SEL_PASSWORD, "pw") in fills

    assert PageEvent("fill", TBankConnector.SEL_OTP, "9999") in fills
    assert [event.argument for event in page.log if event.kind == "type"] == ["1234"]
    assert c.is_logged_in(page) is True


def test_wrong_otp_reprompts_with_rejection_message() -> None:
    c = _connector()
    c.to_worker.put(("sms", "1111"))
    c.to_worker.put(("sms", "2222"))
    page = FakePage(scenario="fresh", wrong_codes={"1111"})
    c.ensure_logged_in(page)
    otp_fills = [
        event.value
        for event in page.log
        if event.kind == "fill" and event.argument == TBankConnector.SEL_OTP
    ]
    assert "1111" in otp_fills
    assert "2222" in otp_fills
    messages: list[str] = []
    while not c.from_worker.empty():
        kind, payload = c.from_worker.get()
        if kind == "sms_required":
            assert isinstance(payload, str)
            messages.append(payload)
    assert messages == [
        "enter the code sent by the bank",
        "the bank rejected the code — check it and try again",
    ]


class _BlockedPage(FakePage):
    """
    The bank shows its 'Access blocked' popup over the phone screen —.

    the driver must fail fast with that message, not loop re-entering the phone.
    """

    @override
    def query_selector(self, selector: str) -> FakeElement | None:
        if selector == TBankConnector.SEL_ACCESS_DENIED:
            return FakeElement("")
        if selector == TBankConnector.SEL_ACCESS_DENIED_TITLE:
            return FakeElement("Access blocked")
        if selector == TBankConnector.SEL_ACCESS_DENIED_DESC:
            return FakeElement("Try again later")
        return super().query_selector(selector)


def test_access_denied_popup_fails_fast_with_bank_message() -> None:
    c = _connector()
    page = _BlockedPage(scenario="fresh")
    with pytest.raises(ConnectorError, match="blocked the login: Access blocked"):
        c.ensure_logged_in(page)

    assert not any(event.kind == "fill" for event in page.log)


class _SubmitClickPage:
    """
    A page whose submit-button click raises a chosen error — used to check.

    that _submit swallows a missing-button timeout but surfaces a real failure.
    """

    def __init__(self, error: Exception) -> None:
        self._error = error

    def locator(self, selector: str) -> tbank_mod._Locator:
        assert selector == TBankConnector.SEL_SUBMIT
        error = self._error

        class L:
            @property
            def first(self) -> Self:
                return self

            def click(self, timeout: int | None = None) -> None:
                assert timeout == 5_000
                raise error

        return L()


def test_submit_skips_missing_button_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTimeoutError(Exception):
        pass

    monkeypatch.setattr(tbank_mod, "PlaywrightTimeoutError", FakeTimeoutError)

    _connector().submit(_SubmitClickPage(FakeTimeoutError("no submit button")))


def test_submit_propagates_real_click_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTimeoutError(Exception):
        pass

    monkeypatch.setattr(tbank_mod, "PlaywrightTimeoutError", FakeTimeoutError)

    with pytest.raises(RuntimeError, match="click intercepted"):
        _connector().submit(_SubmitClickPage(RuntimeError("click intercepted")))


def test_operations_url_scopes_to_account_when_set() -> None:
    c = _connector({**CREDS, "account": "5858870594"})
    assert c.operations_url() == TBankConnector.URL_OPERATIONS + "?account=5858870594"


def test_operations_url_defaults_to_all_feed_when_account_absent_or_blank() -> None:
    assert _connector(dict(CREDS)).operations_url() == TBankConnector.URL_OPERATIONS
    assert _connector({**CREDS, "account": ""}).operations_url() == TBankConnector.URL_OPERATIONS

    assert _connector({**CREDS, "account": "   "}).operations_url() == TBankConnector.URL_OPERATIONS
    assert _connector({**CREDS, "account": None}).operations_url() == TBankConnector.URL_OPERATIONS


def test_operations_url_encodes_the_account() -> None:
    c = _connector({**CREDS, "account": "a b&x"})
    assert c.operations_url() == TBankConnector.URL_OPERATIONS + "?account=a%20b%26x"


def test_download_and_parse_returns_rows() -> None:
    c = _connector()
    page = FakePage(scenario="logged_in", export_label="CSV")
    page.stage = "in"
    rows = c.download_and_parse(page, None)
    assert [row.description for row in rows] == ["Lenta", "Okey"]


def test_download_waits_for_the_account_feed_to_settle_before_export() -> None:

    c = _connector()
    page = FakePage(scenario="logged_in", export_label="CSV")
    page.stage = "in"
    c.download_and_parse(page, None)
    assert [event for event in page.log if event.kind == "goto"] == [
        PageEvent("goto", TBankConnector.URL_OPERATIONS, "domcontentloaded"),
    ]
    settled = [event for event in page.log if event.kind == "load_state"]
    assert settled == [PageEvent("load_state", "networkidle")]
    assert page.load_timeout == TBankConnector.LOGIN_TIMEOUT_MS
    assert page.download_timeout == TBankConnector.LOGIN_TIMEOUT_MS


def test_download_without_export_option_raises() -> None:
    c = _connector()

    page = FakePage(scenario="logged_in", csv_hook=False, export_label="missing")
    page.stage = "in"
    with pytest.raises(ConnectorError):
        c.download_and_parse(page, None)


def test_ask_sms_returns_code_and_signals() -> None:
    c = _connector()
    c.to_worker.put(("sms", "4321"))
    assert c.ask_sms() == "4321"
    assert c.from_worker.get()[0] == "sms_required"


def test_ask_sms_cancel_aborts() -> None:
    c = _connector()
    c.to_worker.put(("cancel", None))
    with pytest.raises(ConnectorError):
        c.ask_sms()


def test_await_worker_dispatch() -> None:
    c = _connector()
    from_worker = c.from_worker
    await_worker = c.await_worker

    from_worker.put(("error", "boom"))
    with pytest.raises(ConnectorError):
        await_worker()
    from_worker.put(("sms_required", "x"))
    with pytest.raises(SmsRequiredError):
        await_worker()

    sentinel = SyncResult([])
    from_worker.put(("result", sentinel))
    assert await_worker() is sentinel


def test_resume_sync_without_worker_errors() -> None:
    c = _connector()
    with pytest.raises(ConnectorError):
        c.resume_sync("0000")


def test_close_without_worker_is_noop() -> None:
    _connector().close()


def test_profile_archive_restore_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "profile"
    (src / "Default").mkdir(parents=True)
    (src / "Default" / "Cookies").write_text("secret-cookie")
    c = _connector()
    blob = c.archive_profile(str(src))
    assert isinstance(blob, str)

    dst = tmp_path / "restored"
    dst.mkdir()
    restored = _connector(session={"profile": blob})
    restored.restore_profile(str(dst))
    assert (dst / "Default" / "Cookies").read_text() == "secret-cookie"


def test_restore_profile_without_session_is_noop(tmp_path: Path) -> None:
    dst = tmp_path / "empty"
    dst.mkdir()
    _connector(session=None).restore_profile(str(dst))
    assert list(dst.iterdir()) == []


def test_prune_cache_drops_junk_dirs(tmp_path: Path) -> None:
    root = tmp_path / "p"
    (root / "Default" / "Cache").mkdir(parents=True)
    (root / "Default" / "Cache" / "x").write_text("junk")
    (root / "GPUCache").mkdir()
    (root / "Default" / "Local Storage").mkdir(parents=True)
    TBankConnector.prune_cache(str(root))
    assert not (root / "Default" / "Cache").exists()
    assert not (root / "GPUCache").exists()
    assert (root / "Default" / "Local Storage").exists()


def test_archive_excludes_cache(tmp_path: Path) -> None:
    src = tmp_path / "profile"
    (src / "Cache").mkdir(parents=True)
    (src / "Cache" / "big").write_text("x" * 100)
    (src / "keep.txt").write_text("keep")
    blob = _connector().archive_profile(str(src))
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(blob)), mode="r:gz") as tar:
        names = tar.getnames()
    assert any(n.endswith("keep.txt") for n in names)
    assert not any("Cache" in n for n in names)


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch, page: FakePage) -> None:
    class FakeContext:
        def __init__(self) -> None:
            self.pages = [page]

        def new_page(self) -> FakePage:
            return page

        def close(self) -> None:
            pass

    class FakeChromium:
        def launch_persistent_context(
            self,
            work_dir: str,
            *,
            headless: bool,
            user_agent: str,
            accept_downloads: bool,
            args: list[str],
        ) -> FakeContext:
            page.launch_options = (work_dir, headless, user_agent, accept_downloads, args)
            return FakeContext()

    class FakeP:
        chromium = FakeChromium()

    class FakeCtxMgr:
        def __enter__(self) -> FakeP:
            return FakeP()

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> Literal[False]:
            return False

    module = types.ModuleType("playwright.sync_api")
    module.__dict__["sync_playwright"] = FakeCtxMgr
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)


def test_run_two_phase_produces_rows_and_session(monkeypatch: pytest.MonkeyPatch) -> None:
    page = FakePage(scenario="fresh", export_label="CSV")
    _install_fake_playwright(monkeypatch, page)
    c = _connector()
    with pytest.raises(SmsRequiredError):
        c.sync()
    result = c.resume_sync("5555")
    assert [row.description for row in result.rows] == ["Lenta", "Okey"]
    assert isinstance(result.session, dict)
    assert "profile" in result.session

    assert page.nav_timeout == TBankConnector.LOGIN_TIMEOUT_MS
    assert page.action_timeout == TBankConnector.LOGIN_TIMEOUT_MS
    assert page.launch_options is not None
    work_dir, headless, user_agent, accept_downloads, args = page.launch_options
    assert pathlib.Path(work_dir).name.startswith("tbank-profile-")
    assert headless is True
    assert user_agent == tbank_mod.USER_AGENT
    assert accept_downloads is True
    assert "--disk-cache-size=1" in args


def test_run_missing_playwright_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    c = _connector()
    with pytest.raises(ConnectorError) as e:
        c.sync()
    assert "playwright" in str(e.value).lower()


def test_run_playwright_error_reports_connector_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePlaywrightError(Exception):
        pass

    class AbortedPage(FakePage):
        @override
        def goto(self, url: str, wait_until: str | None = None) -> None:
            message = "Page.goto: net::ERR_ABORTED"
            raise FakePlaywrightError(message)

    monkeypatch.setattr(tbank_mod, "PlaywrightError", FakePlaywrightError, raising=False)
    _install_fake_playwright(monkeypatch, AbortedPage())
    connector = _connector()
    errors: list[ConnectorError] = []
    finished = threading.Event()

    def run() -> None:
        try:
            connector.sync()
        except ConnectorError as error:
            errors.append(error)
        finally:
            finished.set()

    threading.Thread(target=run, daemon=True).start()

    assert finished.wait(1), "connector remained blocked after its worker failed"
    assert len(errors) == 1
    assert "net::ERR_ABORTED" in str(errors[0])


def test_run_worker_without_message_reports_connector_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(TBankConnector, "_run", lambda _self, _since: None)

    with pytest.raises(ConnectorError, match="worker stopped without a result"):
        _connector().sync()


def test_shot_writes_when_debug_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MONORI_CONNECTOR_DEBUG", "1")
    monkeypatch.chdir(tmp_path)
    page = FakePage(scenario="logged_in")
    TBankConnector.shot(page, "step")
    assert page.screenshots
    screenshot_path, full_page = page.screenshots[0]
    assert screenshot_path.endswith("tbank-step.png")
    assert full_page is True
    assert (tmp_path / "data" / "tbank-step.html").exists()


def test_fake_connector_rows_are_fresh_copies() -> None:
    rows = _rows()
    assert len(rows) == len(FIXTURE_ROWS) == 2
    assert [row.description for row in rows] == ["Lenta", "Salary"]
    assert rows[0] is not FIXTURE_ROWS[0]


def test_get_connector_class_lookup_and_unknown() -> None:
    assert get_connector_class("fake", "fake").__name__ == "FakeConnector"
    with pytest.raises(ConnectorError):
        get_connector_class("nope", "nope")
