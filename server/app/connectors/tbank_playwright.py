"""T-Bank connector that drives the real web cabinet with Playwright.

This logs into ``www.tbank.ru`` **as you**, downloads the operations export, and
feeds it through the same statement parser as the manual paste import. It talks
to no undocumented JSON API — it clicks the same buttons a person clicks.

Reality notes (read before relying on it):

* This is automated access to your own account. It is a grey area against the
  bank's terms of service; use it on your own account at your own risk.
* The bank requires an OTP on login. The flow pauses at the SMS step and raises
  :class:`SmsRequired`; the router collects the code and calls
  :meth:`resume_sync`. The live browser is kept on a dedicated worker thread for
  the connector's lifetime because Playwright objects are thread-affine.
* The session (browser storage state) is cached encrypted, so later syncs skip
  the OTP until it expires.
* **The selectors below are best-effort placeholders.** The live cabinet's
  markup is not something this code can verify; expect to adjust
  ``SEL_*``/``URL_*`` against the real site the first time you run it.

Requires the optional dependency: ``pip install 'monori-server[connectors]'``
followed by ``playwright install chromium``.
"""

import pathlib
import queue
import tempfile
import threading

from ..importer import parse_statement
from .base import Connector, ConnectorError, SmsRequired, SyncResult, register

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


@register
class TBankPlaywrightConnector(Connector):
    bank = "tbank"
    kind = "playwright"

    URL_LOGIN = "https://www.tbank.ru/login/"
    URL_LOGGED_IN_MARKER = "**/mybank/**"

    SEL_PHONE = "input[name='phone'], input[type='tel']"
    SEL_PHONE_SUBMIT = "button[type='submit']"
    SEL_SMS = "input[name='otp'], input[autocomplete='one-time-code']"
    SEL_SMS_SUBMIT = "button[type='submit']"
    SEL_PASSWORD = "input[name='password'], input[type='password']"
    SEL_PASSWORD_SUBMIT = "button[type='submit']"
    SEL_EXPORT_TRIGGER = "[data-qa-type='export'], a[href*='export']"

    LOGIN_TIMEOUT_MS = 120_000

    def __init__(self, credentials, session=None):
        super().__init__(credentials, session)
        self._worker = None
        self._to_worker: queue.Queue = queue.Queue()
        self._from_worker: queue.Queue = queue.Queue()

    def sync(self, since=None):
        self._worker = threading.Thread(target=self._run, args=(since,), daemon=True)
        self._worker.start()
        return self._await_worker()

    def resume_sync(self, code):
        if self._worker is None or not self._worker.is_alive():
            raise ConnectorError("no login in progress")
        self._to_worker.put(("sms", code))
        return self._await_worker()

    def _await_worker(self):
        kind, payload = self._from_worker.get()
        if kind == "sms_required":
            raise SmsRequired(payload)
        if kind == "error":
            raise ConnectorError(payload)
        if kind == "result":
            return payload
        raise ConnectorError(f"unexpected worker message: {kind}")

    def _ask_sms(self):
        """Signal the router that an OTP is needed and block for the code."""
        self._from_worker.put(("sms_required", "enter the code sent by the bank"))
        kind, code = self._to_worker.get()
        if kind != "sms":
            raise ConnectorError("login aborted")
        return code

    def _run(self, since):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._from_worker.put(
                (
                    "error",
                    "playwright is not installed; run "
                    "`pip install 'monori-server[connectors]'` and `playwright install chromium`",
                )
            )
            return
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                storage = self.session.get("storage_state") if self.session else None
                context = browser.new_context(storage_state=storage, user_agent=USER_AGENT)
                page = context.new_page()
                self._ensure_logged_in(page)
                rows = self._download_and_parse(page, since)
                new_session = {"storage_state": context.storage_state()}
                self._from_worker.put(("result", SyncResult(rows, session=new_session)))
        except SmsRequired:
            raise
        except Exception as e:  # noqa: BLE001 - surfaced to the user as a sync error
            self._from_worker.put(("error", str(e)))

    def _ensure_logged_in(self, page):
        page.goto(self.URL_LOGIN, wait_until="domcontentloaded")
        if self._looks_logged_in(page):
            return
        page.fill(self.SEL_PHONE, self.credentials["phone"])
        page.click(self.SEL_PHONE_SUBMIT)
        code = self._ask_sms()
        page.fill(self.SEL_SMS, code)
        page.click(self.SEL_SMS_SUBMIT)
        if page.query_selector(self.SEL_PASSWORD):
            page.fill(self.SEL_PASSWORD, self.credentials["password"])
            page.click(self.SEL_PASSWORD_SUBMIT)
        page.wait_for_url(self.URL_LOGGED_IN_MARKER, timeout=self.LOGIN_TIMEOUT_MS)

    def _looks_logged_in(self, page):
        try:
            page.wait_for_url(self.URL_LOGGED_IN_MARKER, timeout=5_000)
            return True
        except Exception:  # noqa: BLE001 - a timeout just means we must log in
            return False

    def _download_and_parse(self, page, since):
        with page.expect_download(timeout=self.LOGIN_TIMEOUT_MS) as dl:
            page.click(self.SEL_EXPORT_TRIGGER)
        download = dl.value
        with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
            download.save_as(tmp.name)
            text = pathlib.Path(tmp.name).read_text(encoding="utf-8", errors="replace")
        rows, _ = parse_statement(text)
        return rows
