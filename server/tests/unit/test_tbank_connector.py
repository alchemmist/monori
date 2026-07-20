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
        if not self._present:
            raise RuntimeError("locator not present")
        if self._on_click:
            self._on_click()


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def type(self, text):
        self.page.log.append(("type", text))
        if self.page.stage == "enter_code":
            self.page.stage = "in"


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
    """A minimal, scripted stand-in for a Playwright page."""

    def __init__(
        self,
        *,
        scenario="fresh",
        needs_password=False,
        export_label="CSV",
        csv=STATEMENT,
        wrong_codes=None,
    ):
        self.scenario = scenario
        self.needs_password = needs_password
        self.export_label = export_label
        self.csv = csv
        self.wrong_codes = wrong_codes or set()
        self.last_otp = None
        self.url = ""
        self.log = []
        self.keyboard = FakeKeyboard(self)
        self.download_triggered = False
        self.screenshots = []
        # starting screen depends on the scenario
        self.stage = {"logged_in": "in", "quick": "enter_code"}.get(scenario, "start")

    # navigation -------------------------------------------------------------
    def goto(self, url, wait_until=None):
        self.log.append(("goto", url))
        if url == TB.URL_HOME:
            if self.scenario == "logged_in":
                self.stage, self.url = "in", TB.URL_HOME
            elif self.scenario == "quick":
                self.stage, self.url = "enter_code", TB.URL_HOME
            else:
                self.stage, self.url = "phone", TB.URL_LOGIN  # redirect to login
        elif url == TB.URL_LOGIN:
            self.stage, self.url = "phone", TB.URL_LOGIN
        elif url == TB.URL_OPERATIONS:
            self.stage, self.url = "ops", TB.URL_OPERATIONS

    def wait_for_timeout(self, ms):
        self.log.append(("wait", ms))

    def wait_for_url(self, marker, timeout=None):
        self.log.append(("wait_url", marker))
        self.url = TB.URL_HOME

    # form interaction -------------------------------------------------------
    def fill(self, selector, value):
        self.log.append(("fill", selector, value))
        if selector == TB.SEL_SMS:
            self.last_otp = value

    def click(self, selector):
        self.log.append(("click", selector))
        if self.stage == "phone":
            self.stage = "password" if self.needs_password else "sms"
        elif self.stage == "password":
            self.stage = "sms"
        elif self.stage == "sms":
            self.stage = "setcode"

    def query_selector(self, selector):
        self.log.append(("query", selector))
        present = (selector == TB.SEL_PHONE and self.stage == "phone") or (
            selector == TB.SEL_PASSWORD and self.stage == "password"
        )
        return object() if present else None

    def _visible_texts(self):
        return {
            "enter_code": {TB.TEXT_ENTER_CODE},
            "setcode": {TB.TEXT_SET_CODE},
            "sms_rejected": {TB.TEXTS_OTP_REJECTED[0]},
        }.get(self.stage, set())

    def get_by_text(self, text, exact=False):
        present = any(text in t for t in self._visible_texts())
        if self.stage == "export_open" and text == self.export_label:
            present = True

        def on_click():
            if self.stage == "export_open":
                self.download_triggered = True

        return FakeLocator(self, present, on_click)

    def locator(self, selector):
        present = False
        on_click = None
        if selector == TB.SEL_CODE and self.stage in ("enter_code", "setcode"):
            present = True
        elif selector == TB.SEL_SMS_SUBMIT and self.stage in ("sms", "sms_rejected"):
            present = True

            def on_click():
                self.stage = "sms_rejected" if self.last_otp in self.wrong_codes else "setcode"

        elif selector == f"text={TB.TEXT_SET_CODE_SUBMIT}" and self.stage == "setcode":
            present = True

            def on_click():
                self.stage = "in"

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


def test_has_text_true_false_and_error():
    c = _connector()
    page = FakePage(scenario="quick")
    page.stage = "enter_code"
    assert c._has_text(page, TB.TEXT_ENTER_CODE) is True
    assert c._has_text(page, TB.TEXT_SET_CODE) is False

    class Boom:
        def get_by_text(self, *a, **k):
            raise RuntimeError("x")

    assert c._has_text(Boom(), "x") is False


def test_is_logged_in_requires_mybank_no_code_no_phone():
    c = _connector()
    page = FakePage(scenario="logged_in")
    page.stage, page.url = "in", TB.URL_HOME
    assert c._is_logged_in(page) is True
    # code screen visible -> not logged in
    page.stage = "enter_code"
    assert c._is_logged_in(page) is False
    # off /mybank -> not logged in
    page.stage, page.url = "in", TB.URL_LOGIN
    assert c._is_logged_in(page) is False


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
    # went to home, found itself logged in, never touched the phone field
    assert ("goto", TB.URL_LOGIN) not in page.log
    assert not any(a[0] == "fill" for a in page.log)


def test_quick_login_uses_stored_code():
    c = _connector()
    page = FakePage(scenario="quick")
    c._ensure_logged_in(page)
    assert ("type", "1234") in page.log
    # never fell through to a phone login
    assert ("goto", TB.URL_LOGIN) not in page.log


def test_full_login_sets_code_and_enters_otp():
    c = _connector()
    c._to_worker.put(("sms", "9999"))  # the code the user would submit
    page = FakePage(scenario="fresh")
    c._ensure_logged_in(page)
    fills = [a for a in page.log if a[0] == "fill"]
    assert (("fill", TB.SEL_PHONE, "+70000000000")) in fills
    assert (("fill", TB.SEL_SMS, "9999")) in fills
    # the quick-login code was set on the "create a code" screen
    assert ("type", "1234") in page.log
    assert ("wait_url", TB.URL_LOGGED_IN_MARKER) in page.log


def test_wrong_otp_reprompts_with_rejection_message():
    c = _connector()
    c._to_worker.put(("sms", "1111"))
    c._to_worker.put(("sms", "2222"))
    page = FakePage(scenario="fresh", wrong_codes={"1111"})
    c._ensure_logged_in(page)
    fills = [a for a in page.log if a[0] == "fill"]
    assert ("fill", TB.SEL_SMS, "1111") in fills
    assert ("fill", TB.SEL_SMS, "2222") in fills
    messages = []
    while not c._from_worker.empty():
        kind, payload = c._from_worker.get()
        if kind == "sms_required":
            messages.append(payload)
    assert messages == [
        "enter the code sent by the bank",
        "the bank rejected the code — check it and try again",
    ]


def test_full_login_with_password_step():
    c = _connector()
    c._to_worker.put(("sms", "0000"))
    page = FakePage(scenario="fresh", needs_password=True)
    c._ensure_logged_in(page)
    fills = [a for a in page.log if a[0] == "fill"]
    assert ("fill", TB.SEL_PASSWORD, "pw") in fills


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
    module.TimeoutError = type("TimeoutError", (Exception,), {})
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
