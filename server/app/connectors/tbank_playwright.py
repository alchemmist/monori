"""T-Bank connector that drives the real web cabinet with Playwright.

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

Requires the optional dependency: ``pip install 'monori-server[connectors]'``
followed by ``playwright install chromium``.
"""

import base64
import contextlib
import io
import os
import pathlib
import queue
import shutil
import tarfile
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
    URL_HOME = "https://www.tbank.ru/mybank/"
    URL_OPERATIONS = "https://www.tbank.ru/mybank/operations/"
    URL_LOGGED_IN_MARKER = "**/mybank/**"

    SEL_PHONE = "input[name='phone'], input[type='tel']"
    SEL_PHONE_SUBMIT = "button[type='submit']"
    SEL_PASSWORD = "input[name='password']"
    SEL_PASSWORD_SUBMIT = "button[type='submit']"
    SEL_SMS = "input[name='otp'], input[autocomplete='one-time-code']"
    SEL_SMS_SUBMIT = "button[type='submit']"
    # the 4-box code widget on both the "create a code" and "enter code" screens
    SEL_CODE = "input[autocomplete='one-time-code'], input[inputmode='numeric']"
    # the operations page: a period switcher and an export dropdown whose format
    # items (CSV/Excel/PDF) only render once the dropdown is opened
    SEL_PERIOD_YEAR = "[data-qa-type='period-tab-Год']"
    SEL_EXPORT_TRIGGER = "[data-qa-type='molecule-export-dropdown-operations-button']"
    EXPORT_FORMAT_LABELS = ("CSV", "Выгрузить в CSV", "CSV-файл", "Excel")

    TEXT_SET_CODE = "Придумайте код"
    TEXT_ENTER_CODE = "Введите код"
    TEXT_SET_CODE_SUBMIT = "Установить"

    LOGIN_TIMEOUT_MS = 45_000

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

    def close(self):
        # unblock a worker parked on the OTP prompt; it aborts the login, which
        # closes the browser as its `with` blocks unwind, then the thread exits
        if self._worker is not None and self._worker.is_alive():
            self._to_worker.put(("cancel", None))
            self._worker.join(timeout=10)

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
        # The reusable authenticated state (cookies, trusted-device identity)
        # lives only inside the encrypted session blob. Restore it into an
        # owner-only temp dir for the run, then re-archive and hand it back
        # encrypted; the plaintext profile never outlives the sync.
        # mkdtemp already creates the directory owner-only (0700)
        work_dir = tempfile.mkdtemp(prefix="tbank-profile-")
        try:
            self._restore_profile(work_dir)
            with sync_playwright() as p:
                args = ["--disk-cache-size=1"]
                if getattr(os, "geteuid", lambda: -1)() == 0:
                    # chromium refuses to sandbox as root (the in-container case)
                    args.append("--no-sandbox")
                context = p.chromium.launch_persistent_context(
                    work_dir,
                    headless=self._headless(),
                    user_agent=USER_AGENT,
                    accept_downloads=True,
                    args=args,
                )
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    self._ensure_logged_in(page)
                    rows = self._download_and_parse(page, since)
                except Exception:
                    self._save_debug(page)
                    raise
                finally:
                    context.close()
                session = {"profile": self._archive_profile(work_dir)}
                self._from_worker.put(("result", SyncResult(rows, session=session)))
        except Exception as e:  # noqa: BLE001 - surfaced to the user as a sync error
            self._from_worker.put(("error", str(e)))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _restore_profile(self, work_dir):
        blob = self.session.get("profile") if self.session else None
        if not blob:
            return
        with contextlib.suppress(Exception):
            raw = base64.b64decode(blob)
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
                tar.extractall(work_dir, filter="data")

    def _archive_profile(self, work_dir):
        self._prune_cache(work_dir)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(work_dir, arcname=".")
        return base64.b64encode(buf.getvalue()).decode()

    @staticmethod
    def _prune_cache(work_dir):
        """Drop Chromium cache dirs before archiving so the encrypted session
        blob stays small — only cookies/localStorage/IndexedDB matter."""
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
                    shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                    dirs.remove(d)

    @staticmethod
    def _headless():
        return os.environ.get("MONORI_CONNECTOR_HEADED") not in ("1", "true")

    @staticmethod
    def _debug_on():
        return bool(os.environ.get("MONORI_CONNECTOR_DEBUG"))

    @classmethod
    def _shot(cls, page, name):
        if not cls._debug_on():
            return
        out = pathlib.Path("data")
        # a debugging aid must never mask the real error
        with contextlib.suppress(Exception):
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / f"tbank-{name}.png"), full_page=True)
            (out / f"tbank-{name}.html").write_text(
                f"<!-- url: {page.url} -->\n{page.content()}", encoding="utf-8"
            )

    def _save_debug(self, page):
        self._shot(page, "error")

    @staticmethod
    def _has_text(page, text):
        try:
            return page.get_by_text(text, exact=False).count() > 0
        except Exception:  # noqa: BLE001 - treat a query failure as "not present"
            return False

    def _is_logged_in(self, page):
        return (
            "/mybank" in page.url
            and not self._has_text(page, self.TEXT_ENTER_CODE)
            and not self._has_text(page, self.TEXT_SET_CODE)
            and page.query_selector(self.SEL_PHONE) is None
        )

    def _type_code(self, page, code):
        """Enter the 4-digit quick-login code into the code widget."""
        # some widgets grab keystrokes without a focusable box
        with contextlib.suppress(Exception):
            page.locator(self.SEL_CODE).first.click(timeout=5_000)
        page.keyboard.type(code)
        page.wait_for_timeout(1_000)

    def _dismiss_interstitials(self, page):
        for label in ("Не сейчас", "Пропустить", "Позже", "Закрыть"):
            # the label just isn't on this screen
            with contextlib.suppress(Exception):
                page.locator(f"text={label}").first.click(timeout=3_000)
                page.wait_for_timeout(1_000)

    def _ensure_logged_in(self, page):
        page.goto(self.URL_HOME, wait_until="domcontentloaded")
        page.wait_for_timeout(1_500)
        self._shot(page, "01-open")
        if self._is_logged_in(page):
            return

        # Known device, expired session: quick-login with the stored code.
        code = self.credentials.get("code")
        if code and self._has_text(page, self.TEXT_ENTER_CODE):
            self._type_code(page, code)
            self._shot(page, "02-quicklogin")
            if self._is_logged_in(page):
                return

        # Full login on a fresh device.
        page.goto(self.URL_LOGIN, wait_until="domcontentloaded")
        self._shot(page, "03-login")
        page.fill(self.SEL_PHONE, self.credentials["phone"])
        page.click(self.SEL_PHONE_SUBMIT)
        page.wait_for_timeout(1_500)
        if page.query_selector(self.SEL_PASSWORD):
            page.fill(self.SEL_PASSWORD, self.credentials["password"])
            page.click(self.SEL_PASSWORD_SUBMIT)
            self._shot(page, "04-after-password")
        otp = self._ask_sms()
        page.fill(self.SEL_SMS, otp)
        page.click(self.SEL_SMS_SUBMIT)
        page.wait_for_timeout(2_000)
        self._shot(page, "05-after-sms")

        # Right after the OTP the bank offers to set a quick-login code — set ours
        # (and remember it) so future syncs skip the SMS, instead of skipping it.
        if code and self._has_text(page, self.TEXT_SET_CODE):
            self._type_code(page, code)
            # layout varies; screenshots show what happened
            with contextlib.suppress(Exception):
                page.locator(f"text={self.TEXT_SET_CODE_SUBMIT}").first.click(timeout=3_000)
                page.wait_for_timeout(1_000)
                # some flows confirm the code by entering it a second time
                if self._has_text(page, self.TEXT_SET_CODE):
                    self._type_code(page, code)
            self._shot(page, "06-set-code")
        else:
            self._dismiss_interstitials(page)

        # The session is live once the OTP is accepted, but the bank may park
        # us on any number of post-login screens (code confirmations, promos)
        # instead of redirecting. Wait briefly, then force our way home rather
        # than trying to know every screen.
        with contextlib.suppress(Exception):
            page.wait_for_url(self.URL_LOGGED_IN_MARKER, timeout=15_000)
        if not self._is_logged_in(page):
            self._dismiss_interstitials(page)
            page.goto(self.URL_HOME, wait_until="domcontentloaded")
            page.wait_for_timeout(2_500)
        self._shot(page, "07-logged-in")
        if not self._is_logged_in(page):
            raise ConnectorError("login did not reach the bank home page")

    def _download_and_parse(self, page, since):
        page.goto(self.URL_OPERATIONS, wait_until="domcontentloaded")
        page.wait_for_timeout(2_500)
        # widen the shown range to a year so a sync pulls more than the default
        with contextlib.suppress(Exception):
            page.locator(self.SEL_PERIOD_YEAR).first.click(timeout=3_000)
            page.wait_for_timeout(1_500)
        self._shot(page, "08-operations")

        # open the export dropdown, then pick a CSV format inside it
        page.locator(self.SEL_EXPORT_TRIGGER).first.click(timeout=self.LOGIN_TIMEOUT_MS)
        page.wait_for_timeout(1_000)
        self._shot(page, "09-export-menu")
        with page.expect_download(timeout=self.LOGIN_TIMEOUT_MS) as dl:
            if not self._click_export_format(page):
                raise ConnectorError("could not find a CSV export option in the dropdown")
        download = dl.value

        with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
            download.save_as(tmp.name)
            text = pathlib.Path(tmp.name).read_text(encoding="utf-8", errors="replace")
        rows, _ = parse_statement(text)
        return rows

    def _click_export_format(self, page):
        for label in self.EXPORT_FORMAT_LABELS:
            # try the next candidate label if this one isn't in the dropdown
            with contextlib.suppress(Exception):
                page.get_by_text(label, exact=False).first.click(timeout=2_500)
                return True
        return False
