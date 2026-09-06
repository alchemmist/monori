"""Shared _Playwright connector lifecycle and browser interfaces."""

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
from types import TracebackType
from typing import Literal, Protocol, Self, override, runtime_checkable

from monori.common import JsonObject, JsonValue
from monori.server.app.connectors.base import (
    Connector,
    ConnectorChallenge,
    ConnectorError,
    PublicConnectorError,
    SmsRequiredError,
    SyncResult,
    SyncRow,
)


class MissingPlaywrightError(Exception):
    """Stand in for _Playwright errors when the optional dependency is absent."""


class MissingPlaywrightTimeoutError(MissingPlaywrightError):
    """Stand in for _Playwright timeout errors when the dependency is absent."""


PlaywrightError: type[Exception]
PlaywrightTimeoutError: type[Exception]

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
    PlaywrightError = MissingPlaywrightError
    PlaywrightTimeoutError = MissingPlaywrightTimeoutError


class _Locator(Protocol):
    """_Locator operations used by browser connectors."""

    @property
    def first(self) -> Self: ...

    def nth(self, index: int) -> Self: ...

    def click(self, *, timeout: int | None = None) -> None: ...

    def count(self) -> int: ...

    def fill(self, value: str, *, timeout: int | None = None) -> None: ...

    @property
    def content_frame(self) -> "_FrameLocator": ...


class _FrameLocator(Protocol):
    """Frame operations used by browser connectors."""

    def locator(self, selector: str) -> _Locator: ...


class _Keyboard(Protocol):
    """_Keyboard operations used by browser connectors."""

    def type(self, text: str) -> None: ...

    def press(self, key: str) -> None: ...


class _Element(Protocol):
    """_Element operations used by browser connectors."""

    def inner_text(self) -> str: ...


class _Download(Protocol):
    """Downloaded file exposed by _Playwright."""

    def save_as(self, path: str) -> None: ...


class _DownloadExpectation(Protocol):
    """Context manager exposing a completed download."""

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> bool | None: ...

    @property
    def value(self) -> _Download: ...


class _Page(Protocol):
    """Browser page interface shared by bank adapters."""

    @property
    def url(self) -> str: ...

    @property
    def keyboard(self) -> _Keyboard: ...

    def set_default_navigation_timeout(self, timeout: int) -> None: ...

    def set_default_timeout(self, timeout: int) -> None: ...

    def goto(
        self,
        url: str,
        *,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] | None = None,
    ) -> None: ...

    def wait_for_timeout(self, timeout: int) -> None: ...

    def wait_for_load_state(
        self,
        state: Literal["domcontentloaded", "load", "networkidle"],
        *,
        timeout: int | None = None,
    ) -> None: ...

    def fill(self, selector: str, value: str) -> None: ...

    def query_selector(self, selector: str) -> _Element | None: ...

    def get_by_text(self, text: str, *, exact: bool = False) -> _Locator: ...

    def locator(self, selector: str) -> _Locator: ...

    def expect_download(self, *, timeout: int | None = None) -> _DownloadExpectation: ...

    def screenshot(self, *, path: str, full_page: bool = False) -> bytes: ...

    def content(self) -> str: ...

    def evaluate(self, expression: str) -> JsonValue: ...


class _BrowserContext(Protocol):
    """Persistent browser context used by the lifecycle."""

    @property
    def pages(self) -> list[_Page]: ...

    def new_page(self) -> _Page: ...

    def close(self) -> None: ...


class _Chromium(Protocol):
    """_Chromium launcher used by the lifecycle."""

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
    """_Playwright entry point used by the lifecycle."""

    @property
    def chromium(self) -> _Chromium: ...


class _PlaywrightContextManager(Protocol):
    """Context manager returned by sync_playwright."""

    def __enter__(self) -> _Playwright: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> bool | None: ...


@runtime_checkable
class _SyncPlaywright(Protocol):
    """Factory interface returned by the optional _Playwright package."""

    def __call__(self) -> _PlaywrightContextManager: ...


type Page = _Page
type FrameLocator = _FrameLocator
type Locator = _Locator


def load_sync_playwright() -> _SyncPlaywright:
    """Load _Playwright lazily so non-browser installations can import connectors."""
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


type ToWorkerMessage = tuple[Literal["sms"], str] | tuple[Literal["cancel"], None]
type FromWorkerMessage = tuple[str, ConnectorChallenge | SyncResult | str]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


class PlaywrightConnector(Connector):
    """Run a bank adapter with browser lifecycle and profile persistence."""

    LOGIN_TIMEOUT_MS = 45_000
    debug_name = "connector"

    def __init__(
        self,
        credentials: JsonObject | None,
        session: JsonObject | None = None,
        account_ref: str | None = None,
    ) -> None:
        """Initialize the browser worker queues."""
        super().__init__(credentials, session, account_ref)
        self._worker: threading.Thread | None = None
        self.to_worker: queue.Queue[ToWorkerMessage] = queue.Queue()
        self.from_worker: queue.Queue[FromWorkerMessage] = queue.Queue()

    @override
    def sync(self, since: str | None = None) -> SyncResult:
        """Start a browser sync and wait for a result or challenge."""
        self._worker = threading.Thread(target=self._run, args=(since,), daemon=True)
        self._worker.start()
        return self.await_worker()

    @override
    def resume_sync(self, code: str) -> SyncResult:
        """Resume the parked browser worker with user input."""
        if self._worker is None or not self._worker.is_alive():
            msg = "no login in progress"
            raise ConnectorError(msg)
        self.to_worker.put(("sms", code))
        return self.await_worker()

    @override
    def close(self) -> None:
        """Stop a parked browser worker."""
        if self._worker is not None and self._worker.is_alive():
            self.to_worker.put(("cancel", None))
            self._worker.join(timeout=10)

    def await_worker(self) -> SyncResult:
        """Wait for the next browser worker event."""
        while True:
            try:
                kind, payload = self.from_worker.get_nowait()
                return self._decode_worker_event(kind, payload)
            except queue.Empty:
                if self._worker is None:
                    msg = "connector worker stopped without a result"
                    raise ConnectorError(msg) from None
                if not self._worker.is_alive():
                    msg = "connector worker stopped without a result"
                    raise ConnectorError(msg) from None
                self._worker.join(timeout=0.1)

    @staticmethod
    def _decode_worker_event(
        kind: str, payload: ConnectorChallenge | SyncResult | str
    ) -> SyncResult:
        if kind == "sms_required" and isinstance(payload, ConnectorChallenge):
            raise SmsRequiredError(payload)
        if kind == "error" and isinstance(payload, str):
            raise ConnectorError(payload)
        if kind == "public_error" and isinstance(payload, str):
            raise PublicConnectorError(payload)
        if kind == "result" and isinstance(payload, SyncResult):
            return payload
        msg = f"unexpected worker event: {kind}"
        raise ConnectorError(msg)

    def ask_sms(self, challenge: ConnectorChallenge | None = None) -> str:
        """Park the browser worker until the user provides challenge input."""
        self.from_worker.put(
            (
                "sms_required",
                challenge
                or ConnectorChallenge(
                    kind="code",
                    prompt="Enter the code sent by the bank.",
                    can_resend=True,
                ),
            )
        )
        kind, code = self.to_worker.get()
        if kind != "sms" or code is None:
            msg = "login aborted"
            raise ConnectorError(msg)
        return code

    def _run(self, since: str | None) -> None:
        try:
            playwright = load_sync_playwright()
        except ConnectorError as error:
            self.from_worker.put(("error", str(error)))
            return
        work_dir = tempfile.mkdtemp(prefix=f"{self.debug_name}-profile-")
        try:
            self.restore_profile(work_dir)
            with playwright() as runtime:
                args = ["--disk-cache-size=1"]
                if getattr(os, "geteuid", lambda: -1)() == 0:
                    args.append("--no-sandbox")
                context = runtime.chromium.launch_persistent_context(
                    work_dir,
                    headless=self.headless(),
                    user_agent=USER_AGENT,
                    accept_downloads=True,
                    args=args,
                )
                page = context.pages[0] if context.pages else context.new_page()
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
        except PublicConnectorError as error:
            self.from_worker.put(("public_error", str(error)))
        except (
            ConnectorError,
            PlaywrightError,
            OSError,
            RuntimeError,
            ValueError,
            tarfile.TarError,
        ) as error:
            self.from_worker.put(("error", str(error)))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def restore_profile(self, work_dir: str) -> None:
        """Restore the saved _Chromium profile."""
        blob = self.session.get("profile") if self.session else None
        if not isinstance(blob, str) or not blob:
            return
        with contextlib.suppress(Exception):
            raw = base64.b64decode(blob)
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
                archive.extractall(work_dir, filter="data")

    def archive_profile(self, work_dir: str) -> str:
        """Archive the _Chromium profile for encrypted session storage."""
        self.prune_cache(work_dir)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            archive.add(work_dir, arcname=".")
        return base64.b64encode(buffer.getvalue()).decode()

    @staticmethod
    def prune_cache(work_dir: str) -> None:
        """Remove disposable _Chromium caches before archiving a profile."""
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
            for directory in list(dirs):
                if directory in junk:
                    shutil.rmtree(pathlib.Path(root) / directory, ignore_errors=True)
                    dirs.remove(directory)

    @staticmethod
    def headless() -> bool:
        """Return whether _Chromium should run without a visible window."""
        return os.environ.get("MONORI_CONNECTOR_HEADED") not in ("1", "true")

    @staticmethod
    def debug_on() -> bool:
        """Return whether browser snapshots are enabled."""
        return bool(os.environ.get("MONORI_CONNECTOR_DEBUG"))

    @classmethod
    def shot(cls, page: _Page, name: str) -> None:
        """Save a browser snapshot when connector debugging is enabled."""
        if not cls.debug_on():
            return
        output = pathlib.Path("data")
        with contextlib.suppress(Exception):
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / f"{cls.debug_name}-{name}.png"), full_page=True)
            (output / f"{cls.debug_name}-{name}.html").write_text(
                f"<!-- url: {page.url} -->\n{page.content()}", encoding="utf-8"
            )

    def _save_debug(self, page: _Page) -> None:
        self.shot(page, "error")

    def ensure_logged_in(self, page: _Page) -> None:
        """Drive the bank-specific login flow."""
        raise NotImplementedError

    def download_and_parse(self, page: _Page, since: str | None) -> list[SyncRow]:
        """_Download and parse bank-specific transactions."""
        raise NotImplementedError
