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
from urllib.parse import quote

from ..importer import parse_statement
from .base import Connector, ConnectorError, SmsRequired, SyncResult, register

try:
    # playwright is an optional dependency (see _run); when it is installed we
    # catch its real timeout so only a missing element is skipped. Without the
    # extra the connector can't run a live sync at all, so this fallback type is
    # only ever hit by the flow unit tests, which drive a fake page.
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
    PlaywrightTimeoutError = Exception

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


@register
class TBankPlaywrightConnector(Connector):
    bank = "tbank"
    kind = "playwright"
    label = "T-Bank (browser sync)"
    connection_params = [
        {"name": "phone", "label": "Phone", "secret": False, "required": True},
        {"name": "password", "label": "Password", "secret": True, "required": True},
    ]
    account_params = [
        {
            "name": "account",
            "label": "T-Bank account number (optional)",
            "required": False,
            "help": "The number from the account's operations link in the cabinet"
            " (/mybank/operations/?account=<id>); scopes the sync to that one"
            " account. Leave empty for the default feed.",
        }
    ]

    URL_LOGIN = "https://www.tbank.ru/auth/login/"
    URL_HOME = "https://www.tbank.ru/mybank/"
    URL_OPERATIONS = "https://www.tbank.ru/mybank/operations/"

    # The login is the id.tbank.ru SSO: every step is a card at /auth/step with a
    # heading in [automation-id='form-title'] and a single submit in
    # [automation-id='button-submit']. There are three input screens — phone,
    # password, and a 4-box pin widget reused for BOTH the SMS code and the
    # quick-login code. We drive it as a state machine keyed on which field is on
    # screen (and the title, to tell "set a code" from "enter a code"), rather
    # than a fixed phone→password→sms sequence, so slow renders or a reordered
    # step can't make us skip one.
    SEL_PHONE = "[automation-id='phone-input']"
    SEL_PASSWORD = "[automation-id='password-input']"
    # the SMS code screen is a single one-time-code input (auto-submits on the
    # last digit) — distinct from the 4-box pin widget used to set/enter the
    # quick-login code
    SEL_OTP = "[automation-id='otp-input']"
    SEL_PIN = "[automation-id='pin-code-input-0']"
    SEL_SUBMIT = "[automation-id='button-submit']"
    SEL_FORM_TITLE = "[automation-id='form-title']"
    # the bank's "Доступ заблокирован" popup (anti-automation / rate limit); it
    # sits over the phone screen, so the driver must detect it and stop rather
    # than re-entering the phone until the step loop is exhausted
    SEL_ACCESS_DENIED = "[automation-id='access-denied-popup']"
    SEL_ACCESS_DENIED_TITLE = "[automation-id='access-denied-title']"
    SEL_ACCESS_DENIED_DESC = "[automation-id='access-denied-description']"
    # the operations page: an export dropdown whose format items only render once
    # the dropdown is opened. Each item carries a stable per-format hook — CSV is
    # the one the statement parser consumes. data-qa-type is a space-joined token
    # list ("click-area … menuItem menuItem-csv"), so match the token with ~=.
    SEL_EXPORT_TRIGGER = "[data-qa-type='molecule-export-dropdown-operations-button']"
    SEL_EXPORT_CSV = "[data-qa-type~='molecule-export-dropdown-operations-menuItem-csv']"
    # fall back to a visible CSV label only if that hook ever changes; every
    # candidate is a CSV variant (xlsx/ofx would break the CSV statement parser)
    EXPORT_FORMAT_LABELS = ("Скачать в CSV", "Выгрузить в CSV", "CSV-файл", "CSV")

    # form-title text that distinguishes the "create a quick-login code" screen
    # from the "enter a code" screens (SMS or quick-login)
    TITLE_SET_CODE = "Придумайте код"

    LOGIN_STEPS = 24
    STEP_PAUSE_MS = 2_500
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

    def _ask_sms(self, message="enter the code sent by the bank"):
        """Signal the router that an OTP is needed and block for the code."""
        self._from_worker.put(("sms_required", message))
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
                # the authenticated /mybank SPA can take well over Playwright's
                # default 30s to reach domcontentloaded (seen as a goto timeout on
                # retry) — give navigations and actions the full login budget
                page.set_default_navigation_timeout(self.LOGIN_TIMEOUT_MS)
                page.set_default_timeout(self.LOGIN_TIMEOUT_MS)
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

    def _is_logged_in(self, page):
        # the authenticated app lives under /mybank while the SSO login stays on
        # id.tbank.ru/auth/step — but the bank can also re-park a code prompt over
        # a /mybank URL, so require both: the /mybank path AND no login step still
        # on screen, or the driver would stop early on a prompt it hasn't cleared
        if "/mybank" not in page.url:
            return False
        return not (
            page.query_selector(self.SEL_PHONE)
            or page.query_selector(self.SEL_PASSWORD)
            or page.query_selector(self.SEL_OTP)
            or page.query_selector(self.SEL_PIN)
        )

    def _access_denied(self, page):
        """The bank's "Доступ заблокирован" popup text when it's shown, else ''.
        It blocks the phone screen (anti-automation / rate limit), so the driver
        checks for it first and fails fast with the bank's own wording."""
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

    def _form_title(self, page):
        """The heading of the current SSO step, or '' when none is shown."""
        with contextlib.suppress(Exception):
            el = page.query_selector(self.SEL_FORM_TITLE)
            if el is not None:
                return (el.inner_text() or "").strip()
        return ""

    def _submit(self, page):
        """Click the step's submit button. Some layouts auto-advance as the last
        digit lands, so a genuinely-absent button times out and is skipped — but
        a real click failure (detached node, intercepted click) still surfaces."""
        with contextlib.suppress(PlaywrightTimeoutError):
            page.locator(self.SEL_SUBMIT).first.click(timeout=5_000)

    def _type_pin(self, page, digits):
        """Type into the 4-box pin widget used for both the SMS code and the
        quick-login code. Focusing the first box and typing lets it auto-advance
        across the boxes."""
        with contextlib.suppress(Exception):
            page.locator(self.SEL_PIN).first.click(timeout=5_000)
        page.keyboard.type(digits)
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
        # a cold visit to /mybank bounces to id.tbank.ru; make sure we're on the
        # SSO before driving it (goto is a no-op if we're already there)
        on_sso = (
            page.query_selector(self.SEL_PHONE)
            or page.query_selector(self.SEL_OTP)
            or page.query_selector(self.SEL_PIN)
        )
        if not on_sso:
            page.goto(self.URL_LOGIN, wait_until="domcontentloaded")
            page.wait_for_timeout(1_500)
        self._shot(page, "02-login")
        self._drive_sso_login(page)
        self._shot(page, "09-logged-in")
        if not self._is_logged_in(page):
            # name the screen we're stuck on so the failure points at the real
            # step (a wrong selector, an unhandled prompt) instead of being generic
            where = self._form_title(page) or page.url or "unknown screen"
            raise ConnectorError(f"login did not reach the bank home page (stuck on: {where})")

    def _drive_sso_login(self, page):
        """Walk the id.tbank.ru SSO one step at a time until we reach /mybank.

        Each iteration reacts to whatever step is on screen — phone, password, or
        the pin widget (set-a-code / enter-a-code) — so a slow render or a
        reordered step just means another pass, never a skipped field."""
        code = self.credentials.get("code")
        tried_quick = False
        otp_prompt = "enter the code sent by the bank"
        for step in range(self.LOGIN_STEPS):
            if self._is_logged_in(page):
                return
            blocked = self._access_denied(page)
            if blocked:
                raise ConnectorError(f"the bank blocked the login: {blocked}")
            if page.query_selector(self.SEL_PHONE):
                page.fill(self.SEL_PHONE, self.credentials["phone"])
                self._submit(page)
            elif page.query_selector(self.SEL_PASSWORD):
                page.fill(self.SEL_PASSWORD, self.credentials["password"])
                self._submit(page)
            elif page.query_selector(self.SEL_OTP):
                # the SMS one-time code: surface the input to the user right away,
                # then type it into the single otp field (it auto-submits on the
                # last digit). If the same screen is still up next pass the code was
                # rejected, so we ask again with the rejection message.
                otp = self._ask_sms(otp_prompt)
                otp_prompt = "the bank rejected the code — check it and try again"
                page.fill(self.SEL_OTP, otp)
                self._submit(page)
            elif page.query_selector(self.SEL_PIN):
                title = self._form_title(page)
                if self.TITLE_SET_CODE in title:
                    # the bank wants us to create a quick-login code — set the one
                    # the server generated (and stored) so future syncs skip SMS
                    self._type_pin(page, code)
                    self._submit(page)
                elif code and not tried_quick:
                    # trusted device, expired session: quick-login with the stored
                    # code. Try it once — if it's stale the screen persists and we
                    # fall through (to the phone / SMS path) instead of looping.
                    self._type_pin(page, code)
                    self._submit(page)
                    tried_quick = True
                else:
                    self._dismiss_interstitials(page)
                    page.goto(self.URL_HOME, wait_until="domcontentloaded")
            else:
                # an interstitial (promo, "not now") between steps — clear it and
                # nudge back toward home
                self._dismiss_interstitials(page)
                page.goto(self.URL_HOME, wait_until="domcontentloaded")
            page.wait_for_timeout(self.STEP_PAUSE_MS)
            self._shot(page, f"step-{step:02d}")

    def _operations_url(self):
        # scope the export to a single T-Bank account when the connection names
        # one (the cabinet's own per-account link is
        # /mybank/operations/?account=<id>, e.g. the Black debit 5858870594);
        # without it the page exports the default all-accounts feed. Each monori
        # account maps to its own connection, so a savings account is just
        # another connection with its own id.
        account = self.account_ref or (self.credentials or {}).get("account")
        # a whitespace-only id is not a real account — strip before deciding, so
        # stored creds from a non-web client can't scope us to ...?account=%20
        account = str(account).strip() if account is not None else ""
        if account:
            return f"{self.URL_OPERATIONS}?account={quote(account, safe='')}"
        return self.URL_OPERATIONS

    def _download_and_parse(self, page, since):
        page.goto(self._operations_url(), wait_until="domcontentloaded")
        page.wait_for_timeout(2_500)
        self._shot(page, "08-operations")

        # The feed's default period (the current month) is what's exported. The
        # "Год" period tab lives in a collapsed analytics widget that stays
        # visibility:hidden here and doesn't drive the export, so there's nothing
        # to click — overlapping syncs are deduped by row hash downstream, so a
        # regular sync misses nothing.
        # open the export dropdown, then pick the CSV format inside it
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
        # prefer the stable per-format hook (reliable even when a "CSV" substring
        # shows up elsewhere on the page); fall back to a visible label only if
        # the markup drifts. Both target CSV — what the statement parser reads.
        with contextlib.suppress(Exception):
            page.locator(self.SEL_EXPORT_CSV).first.click(timeout=5_000)
            return True
        for label in self.EXPORT_FORMAT_LABELS:
            # try the next candidate label if this one isn't in the dropdown
            with contextlib.suppress(Exception):
                page.get_by_text(label, exact=False).first.click(timeout=2_500)
                return True
        return False
