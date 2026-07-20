"""Unit tests for the T-Bank Playwright connector's flow logic.

The real browser is replaced by a scripted fake page/context, so the login
sequence, selectors, quick-login-code handling, statement download and the
encrypted-profile round-trip are all exercised without Chromium or the bank.
"""

import base64
import io
import pathlib
import sys
import tarfile
import types

import pytest

from app.connectors import tbank_playwright as tbank_mod
from app.connectors.base import ConnectorError, SmsRequired
from app.connectors.tbank_playwright import TBankPlaywrightConnector as TB

STATEMENT = (
    "05.01.2026 10:00:00\t05.01.2026\t*1\tOK\t-100,00\tRUB\t-100,00\tRUB\t\tSuper\t5411\tLenta\t0\t0\t-100,00\n"  # noqa: E501
    "06.01.2026 11:00:00\t06.01.2026\t*1\tOK\t-200,00\tRUB\t-200,00\tRUB\t\tSuper\t5411\tOkey\t0\t0\t-200,00\n"  # noqa: E501
)

CREDS = {"phone": "+70000000000", "password": "pw", "code": "1234"}


class FakeLocator:
    def __init__(self, page, present, on_click=None):
        self.page = page
        self._present = present
        self._on_click = on_click

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self._present else 0

    def click(self, timeout=None):
        # clicking a control that isn't on screen times out in real Playwright —
        # callers that treat a missing button as optional suppress exactly that
        if not self._present:
            raise tbank_mod.PlaywrightTimeoutError("locator not present")
        if self._on_click:
            self._on_click()


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def type(self, text):
        self.page.log.append(("type", text))
        # every code entry (SMS, quick-login, set-code) types into the pin widget;
        # remember it (to recognize a wrong SMS code) and auto-advance as the last
        # digit lands, which is how the real widget submits without a button click
        self.page.last_code = text
        if self.page.stage in self.page.PIN_STAGES:
            self.page._advance()


class FakeElement:
    def __init__(self, text):
        self._text = text

    def inner_text(self):
        return self._text


class FakeDownload:
    def __init__(self, text):
        self._text = text

    def save_as(self, path):
        pathlib.Path(path).write_text(self._text, encoding="utf-8")


class FakeDownloadExpectation:
    def __init__(self, page):
        self.page = page

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def value(self):
        if not self.page.download_triggered:
            raise RuntimeError("no download happened")
        return FakeDownload(self.page.csv)


class FakePage:
    """A scripted stand-in for a Playwright page driving the id.tbank.ru SSO.

    ``stage`` is the current step: phone → password → sms → setcode → in for a
    fresh login, ``quickcode`` for a trusted-device quick login, and in/ops/
    export_open for the post-login statement download. Each login step exposes a
    ``form-title`` and a single submit button; the pin widget backs both the SMS
    code and the quick-login/set-code screens."""

    TITLES = {
        "phone": "Вход в Т-Банк",
        "password": "Введите пароль",
        "sms": "Введите код из СМС",
        "setcode": TB.TITLE_SET_CODE,
        "quickcode": "Введите код",
    }
    PIN_STAGES = ("sms", "setcode", "quickcode")

    def __init__(self, *, scenario="fresh", export_label="CSV", csv=STATEMENT, wrong_codes=None):
        self.scenario = scenario
        self.export_label = export_label
        self.csv = csv
        self.wrong_codes = wrong_codes or set()
        self.last_code = None
        self.url = ""
        self.log = []
        self.keyboard = FakeKeyboard(self)
        self.download_triggered = False
        self.screenshots = []
        self.nav_timeout = None
        self.action_timeout = None
        self.stage = {"logged_in": "in", "quick": "quickcode"}.get(scenario, "start")

    def set_default_navigation_timeout(self, ms):
        self.nav_timeout = ms

    def set_default_timeout(self, ms):
        self.action_timeout = ms

    # navigation -------------------------------------------------------------
    def goto(self, url, wait_until=None):
        self.log.append(("goto", url))
        if url == TB.URL_HOME:
            if self.scenario == "logged_in" or self.stage == "in":
                self.stage, self.url = "in", TB.URL_HOME
            elif self.scenario == "quick":
                self.stage, self.url = "quickcode", TB.URL_LOGIN
            else:
                self.stage, self.url = "phone", TB.URL_LOGIN  # bounces to the SSO
        elif url == TB.URL_LOGIN:
            self.stage = "quickcode" if self.scenario == "quick" else "phone"
            self.url = TB.URL_LOGIN
        elif url == TB.URL_OPERATIONS:
            self.stage, self.url = "ops", TB.URL_OPERATIONS

    def wait_for_timeout(self, ms):
        self.log.append(("wait", ms))

    # form interaction -------------------------------------------------------
    def fill(self, selector, value):
        self.log.append(("fill", selector, value))

    def query_selector(self, selector):
        self.log.append(("query", selector))
        if (
            (selector == TB.SEL_PHONE and self.stage == "phone")
            or (selector == TB.SEL_PASSWORD and self.stage == "password")
            or (selector == TB.SEL_PIN and self.stage in self.PIN_STAGES)
        ):
            return object()
        if selector == TB.SEL_FORM_TITLE and self.stage in self.TITLES:
            return FakeElement(self.TITLES[self.stage])
        return None

    def get_by_text(self, text, exact=False):
        present = self.stage == "export_open" and text == self.export_label

        def on_click():
            if self.stage == "export_open":
                self.download_triggered = True

        return FakeLocator(self, present, on_click)

    def _advance(self):
        if self.stage == "phone":
            self.stage = "password"
        elif self.stage == "password":
            self.stage = "sms"
        elif self.stage == "sms":
            # a correct OTP advances to the set-code screen; a wrong one stays put
            self.stage = "sms" if self.last_code in self.wrong_codes else "setcode"
        elif self.stage in ("setcode", "quickcode"):
            self.stage, self.url = "in", TB.URL_HOME

    def locator(self, selector):
        present = False
        on_click = None
        if selector == TB.SEL_PIN and self.stage in self.PIN_STAGES:
            present = True  # focus target for _type_pin
        elif selector == TB.SEL_SUBMIT and self.stage in (*self.PIN_STAGES, "phone", "password"):
            present = True
            # phone/password submit via the button; the pin widget already
            # auto-advanced on the last digit, so its button click is a no-op
            if self.stage in ("phone", "password"):
                on_click = self._advance
        elif selector == TB.SEL_PERIOD_YEAR and self.stage == "ops":
            present = True
        elif selector == TB.SEL_EXPORT_TRIGGER and self.stage == "ops":
            present = True

            def on_click():
                self.stage = "export_open"

        return FakeLocator(self, present, on_click)

    def expect_download(self, timeout=None):
        return FakeDownloadExpectation(self)

    # debug ------------------------------------------------------------------
    def screenshot(self, path=None, full_page=False):
        self.screenshots.append(path)

    def content(self):
        return "<html></html>"


def _connector(creds=None, session=None):
    return TB(creds if creds is not None else dict(CREDS), session)


# --- pure / logic helpers ---------------------------------------------------


def test_headless_default_and_headed_override(monkeypatch):
    monkeypatch.delenv("MONORI_CONNECTOR_HEADED", raising=False)
    assert TB._headless() is True
    monkeypatch.setenv("MONORI_CONNECTOR_HEADED", "1")
    assert TB._headless() is False


def test_debug_flag(monkeypatch):
    monkeypatch.delenv("MONORI_CONNECTOR_DEBUG", raising=False)
    assert TB._debug_on() is False
    monkeypatch.setenv("MONORI_CONNECTOR_DEBUG", "1")
    assert TB._debug_on() is True


def test_is_logged_in_is_true_only_on_mybank():
    c = _connector()
    page = FakePage(scenario="logged_in")
    page.stage, page.url = "in", TB.URL_HOME
    assert c._is_logged_in(page) is True
    # still on the SSO -> not logged in
    page.url = TB.URL_LOGIN
    assert c._is_logged_in(page) is False


def test_is_logged_in_false_when_a_code_prompt_is_reparked_over_mybank():
    c = _connector()
    page = FakePage(scenario="fresh")
    # the bank shows a pin (set/enter-code) prompt on a /mybank URL — not yet in
    page.stage, page.url = "setcode", TB.URL_HOME
    assert c._is_logged_in(page) is False


def test_form_title_reads_heading_or_empty():
    c = _connector()
    page = FakePage(scenario="fresh")
    page.stage = "password"
    assert c._form_title(page) == "Введите пароль"
    page.stage = "in"  # the app has no SSO form-title element
    assert c._form_title(page) == ""


def test_click_export_format_picks_present_label():
    c = _connector()
    page = FakePage(export_label="CSV")
    page.stage = "export_open"
    assert c._click_export_format(page) is True
    assert page.download_triggered is True


def test_click_export_format_none_present():
    c = _connector()
    page = FakePage(export_label="nope")
    page.stage = "export_open"
    assert c._click_export_format(page) is False
    assert page.download_triggered is False


# --- login flow -------------------------------------------------------------


def test_already_logged_in_skips_login():
    c = _connector()
    page = FakePage(scenario="logged_in")
    c._ensure_logged_in(page)
    # went to home, found itself logged in, never drove the SSO
    assert ("goto", TB.URL_LOGIN) not in page.log
    assert not any(a[0] == "fill" for a in page.log)


def test_quick_login_uses_stored_code():
    c = _connector()
    page = FakePage(scenario="quick")
    c._ensure_logged_in(page)
    assert ("type", "1234") in page.log
    # a trusted-device quick login never fills the phone or password
    assert not any(a[0] == "fill" for a in page.log)


def test_full_login_enters_phone_password_otp_then_sets_code():
    c = _connector()
    c._to_worker.put(("sms", "9999"))  # the SMS code the user would submit
    page = FakePage(scenario="fresh")
    c._ensure_logged_in(page)
    fills = [a for a in page.log if a[0] == "fill"]
    assert ("fill", TB.SEL_PHONE, "+70000000000") in fills
    assert ("fill", TB.SEL_PASSWORD, "pw") in fills
    # the user's SMS code is typed into the pin widget, then our quick-login code
    # is set on the "Придумайте код" screen — in that order
    types = [a[1] for a in page.log if a[0] == "type"]
    assert types == ["9999", "1234"]
    assert c._is_logged_in(page) is True


def test_wrong_otp_reprompts_with_rejection_message():
    c = _connector()
    c._to_worker.put(("sms", "1111"))
    c._to_worker.put(("sms", "2222"))
    page = FakePage(scenario="fresh", wrong_codes={"1111"})
    c._ensure_logged_in(page)
    types = [a[1] for a in page.log if a[0] == "type"]
    assert "1111" in types and "2222" in types
    messages = []
    while not c._from_worker.empty():
        kind, payload = c._from_worker.get()
        if kind == "sms_required":
            messages.append(payload)
    assert messages == [
        "enter the code sent by the bank",
        "the bank rejected the code — check it and try again",
    ]


class _BlockedPage(FakePage):
    """The bank shows its 'Доступ заблокирован' popup over the phone screen —
    the driver must fail fast with that message, not loop re-entering the phone."""

    def query_selector(self, selector):
        if selector == TB.SEL_ACCESS_DENIED:
            return object()
        if selector == TB.SEL_ACCESS_DENIED_TITLE:
            return FakeElement("Доступ заблокирован")
        if selector == TB.SEL_ACCESS_DENIED_DESC:
            return FakeElement("Попробуйте снова позже")
        return super().query_selector(selector)


def test_access_denied_popup_fails_fast_with_bank_message():
    c = _connector()
    page = _BlockedPage(scenario="fresh")
    with pytest.raises(ConnectorError, match="blocked the login: Доступ заблокирован"):
        c._ensure_logged_in(page)
    # it stopped at the block, never entering the phone in a doomed loop
    assert not any(a[0] == "fill" for a in page.log)


class _SubmitClickPage:
    """A page whose submit-button click raises a chosen error — used to check
    that _submit swallows a missing-button timeout but surfaces a real failure."""

    def __init__(self, error):
        self._error = error

    def locator(self, selector):
        error = self._error

        class L:
            @property
            def first(self):
                return self

            def click(self, timeout=None):
                raise error

        return L()


def test_submit_skips_missing_button_timeout(monkeypatch):
    import app.connectors.tbank_playwright as mod

    class FakeTimeout(Exception):
        pass

    monkeypatch.setattr(mod, "PlaywrightTimeoutError", FakeTimeout)
    # a missing/auto-submit button reads as a timeout: _submit swallows it so the
    # pin widget's own auto-submit can carry the step
    _connector()._submit(_SubmitClickPage(FakeTimeout("no submit button")))


def test_submit_propagates_real_click_error(monkeypatch):
    import app.connectors.tbank_playwright as mod

    class FakeTimeout(Exception):
        pass

    monkeypatch.setattr(mod, "PlaywrightTimeoutError", FakeTimeout)
    # a real interaction failure is not a timeout: it must surface, not be
    # swallowed into a broken, silently-continuing login
    with pytest.raises(RuntimeError, match="click intercepted"):
        _connector()._submit(_SubmitClickPage(RuntimeError("click intercepted")))


# --- download ---------------------------------------------------------------


def test_download_and_parse_returns_rows():
    c = _connector()
    page = FakePage(scenario="logged_in", export_label="CSV")
    page.stage = "in"
    rows = c._download_and_parse(page, None)
    assert [r["description"] for r in rows] == ["Lenta", "Okey"]


def test_download_without_export_option_raises():
    c = _connector()
    page = FakePage(scenario="logged_in", export_label="missing")
    page.stage = "in"
    with pytest.raises(ConnectorError):
        c._download_and_parse(page, None)


# --- OTP handshake / worker plumbing ---------------------------------------


def test_ask_sms_returns_code_and_signals():
    c = _connector()
    c._to_worker.put(("sms", "4321"))
    assert c._ask_sms() == "4321"
    assert c._from_worker.get()[0] == "sms_required"


def test_ask_sms_cancel_aborts():
    c = _connector()
    c._to_worker.put(("cancel", None))
    with pytest.raises(ConnectorError):
        c._ask_sms()


def test_await_worker_dispatch():
    c = _connector()
    c._from_worker.put(("error", "boom"))
    with pytest.raises(ConnectorError):
        c._await_worker()
    c._from_worker.put(("sms_required", "x"))
    with pytest.raises(SmsRequired):
        c._await_worker()
    sentinel = object()
    c._from_worker.put(("result", sentinel))
    assert c._await_worker() is sentinel


def test_resume_sync_without_worker_errors():
    c = _connector()
    with pytest.raises(ConnectorError):
        c.resume_sync("0000")


def test_close_without_worker_is_noop():
    _connector().close()  # must not raise


# --- encrypted profile round-trip ------------------------------------------


def test_profile_archive_restore_roundtrip(tmp_path):
    src = tmp_path / "profile"
    (src / "Default").mkdir(parents=True)
    (src / "Default" / "Cookies").write_text("secret-cookie")
    c = _connector()
    blob = c._archive_profile(str(src))
    assert isinstance(blob, str)

    dst = tmp_path / "restored"
    dst.mkdir()
    restored = _connector(session={"profile": blob})
    restored._restore_profile(str(dst))
    assert (dst / "Default" / "Cookies").read_text() == "secret-cookie"


def test_restore_profile_without_session_is_noop(tmp_path):
    dst = tmp_path / "empty"
    dst.mkdir()
    _connector(session=None)._restore_profile(str(dst))
    assert list(dst.iterdir()) == []


def test_prune_cache_drops_junk_dirs(tmp_path):
    root = tmp_path / "p"
    (root / "Default" / "Cache").mkdir(parents=True)
    (root / "Default" / "Cache" / "x").write_text("junk")
    (root / "GPUCache").mkdir()
    (root / "Default" / "Local Storage").mkdir(parents=True)
    TB._prune_cache(str(root))
    assert not (root / "Default" / "Cache").exists()
    assert not (root / "GPUCache").exists()
    assert (root / "Default" / "Local Storage").exists()


def test_archive_excludes_cache(tmp_path):
    src = tmp_path / "profile"
    (src / "Cache").mkdir(parents=True)
    (src / "Cache" / "big").write_text("x" * 100)
    (src / "keep.txt").write_text("keep")
    blob = _connector()._archive_profile(str(src))
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(blob)), mode="r:gz") as tar:
        names = tar.getnames()
    assert any(n.endswith("keep.txt") for n in names)
    assert not any("Cache" in n for n in names)


# --- _run end to end via an injected fake Playwright ------------------------


def _install_fake_playwright(monkeypatch, page):
    class FakeContext:
        def __init__(self):
            self.pages = [page]

        def new_page(self):
            return page

        def close(self):
            pass

    class FakeChromium:
        def launch_persistent_context(self, work_dir, **kw):
            return FakeContext()

    class FakeP:
        chromium = FakeChromium()

    class FakeCtxMgr:
        def __enter__(self):
            return FakeP()

        def __exit__(self, *exc):
            return False

    module = types.ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: FakeCtxMgr()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)


def test_run_two_phase_produces_rows_and_session(monkeypatch):
    page = FakePage(scenario="fresh", export_label="CSV")
    _install_fake_playwright(monkeypatch, page)
    c = _connector()
    with pytest.raises(SmsRequired):
        c.sync()
    result = c.resume_sync("5555")
    assert [r["description"] for r in result.rows] == ["Lenta", "Okey"]
    assert "profile" in result.session
    # navigations get the full login budget, not Playwright's default 30s
    assert page.nav_timeout == TB.LOGIN_TIMEOUT_MS
    assert page.action_timeout == TB.LOGIN_TIMEOUT_MS


def test_run_missing_playwright_reports_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    c = _connector()
    with pytest.raises(ConnectorError) as e:
        c.sync()
    assert "playwright" in str(e.value).lower()


def test_shot_writes_when_debug_on(monkeypatch, tmp_path):
    monkeypatch.setenv("MONORI_CONNECTOR_DEBUG", "1")
    monkeypatch.chdir(tmp_path)
    page = FakePage(scenario="logged_in")
    TB._shot(page, "step")
    assert page.screenshots and page.screenshots[0].endswith("tbank-step.png")
    assert (tmp_path / "data" / "tbank-step.html").exists()


# --- connector registry / fake connector -----------------------------------


def test_fake_connector_rows_have_sha1_hashes():
    from app.connectors.fake import FIXTURE_ROWS, _rows

    rows = _rows()
    assert len(rows) == len(FIXTURE_ROWS) == 2
    assert [r["description"] for r in rows] == ["Lenta", "Salary"]
    assert all(len(r["hash"]) == 40 for r in rows)


def test_get_connector_class_lookup_and_unknown():
    import app.connectors.fake  # noqa: F401  (registers the fake connector)
    from app.connectors.base import get_connector_class

    assert get_connector_class("fake", "fake").__name__ == "FakeConnector"
    with pytest.raises(ConnectorError):
        get_connector_class("nope", "nope")
