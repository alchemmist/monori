import base64
import builtins
import importlib
import queue
import tarfile
from io import BytesIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast
from unittest.mock import Mock, call

import pytest

from monori.common import JsonValue
from monori.server.app.connectors import playwright as playwright_module
from monori.server.app.connectors.base import (
    ConnectorChallenge,
    ConnectorError,
    PublicConnectorError,
    SyncResult,
)
from monori.server.app.connectors.playwright import PlaywrightConnector, ToWorkerMessage


def test_load_rejects_module_without_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        playwright_module.importlib,
        "import_module",
        lambda _name: SimpleNamespace(sync_playwright=object()),
    )
    with pytest.raises(ConnectorError, match="does not provide"):
        playwright_module.load_sync_playwright()


def test_load_reports_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> ModuleType:
        raise ImportError

    monkeypatch.setattr(playwright_module.importlib, "import_module", missing)
    with pytest.raises(ConnectorError) as error:
        playwright_module.load_sync_playwright()
    assert str(error.value) == (
        "playwright is not installed; run `uv sync --group test` and `playwright install chromium`"
    )


def test_worker_lifecycle_handles_wait_close_and_invalid_events() -> None:
    connector = PlaywrightConnector(
        {"login": "person"}, session={"token": "saved"}, account_ref="card"
    )
    assert connector.credentials == {"login": "person"}
    assert connector.session == {"token": "saved"}
    assert connector.account_ref == "card"
    result = SyncResult([])
    connector.from_worker = Mock()
    connector.from_worker.get_nowait.side_effect = [queue.Empty, ("result", result)]
    worker = Mock()
    worker.is_alive.side_effect = [True, True]
    connector.__dict__["_worker"] = worker
    assert connector.await_worker() is result

    connector.close()
    assert connector.to_worker.get_nowait() == ("cancel", None)
    assert worker.join.call_args_list == [call(timeout=0.1), call(timeout=10)]

    connector.from_worker = queue.Queue()
    connector.from_worker.put(("public_error", "safe"))
    with pytest.raises(PublicConnectorError, match="safe"):
        connector.await_worker()
    connector.from_worker.put(("result", "invalid"))
    with pytest.raises(ConnectorError, match="unexpected worker event"):
        connector.await_worker()


def test_worker_wait_fails_when_no_worker_was_started() -> None:
    with pytest.raises(ConnectorError, match="worker stopped without a result"):
        PlaywrightConnector({}).await_worker()


def test_run_reports_public_error_and_uses_root_chromium_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MONORI_CONNECTOR_DEBUG", "1")
    page = Mock()
    page.url = "https://bank.example/error"
    page.content.return_value = "<main>error</main>"
    context = Mock(pages=[page])
    runtime = SimpleNamespace(chromium=Mock())
    runtime.chromium.launch_persistent_context.return_value = context
    manager = Mock()
    manager.__enter__ = Mock(return_value=runtime)
    manager.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(playwright_module, "load_sync_playwright", lambda: lambda: manager)
    monkeypatch.setattr(playwright_module.os, "geteuid", lambda: 0)

    connector = PlaywrightConnector({})
    connector.ensure_logged_in = Mock(side_effect=PublicConnectorError("safe"))
    with pytest.raises(PublicConnectorError, match="safe"):
        connector.sync()

    assert "--no-sandbox" in runtime.chromium.launch_persistent_context.call_args.kwargs["args"]
    assert (tmp_path / "data" / "connector-error.html").read_text() == (
        "<!-- url: https://bank.example/error -->\n<main>error</main>"
    )


def test_successful_run_preserves_arguments_and_cleans_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = Mock()
    context = Mock(pages=[page])
    runtime = SimpleNamespace(chromium=Mock())
    runtime.chromium.launch_persistent_context.return_value = context
    manager = Mock()
    manager.__enter__ = Mock(return_value=runtime)
    manager.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(playwright_module, "load_sync_playwright", lambda: lambda: manager)
    real_rmtree = playwright_module.shutil.rmtree
    cleanup = Mock(side_effect=real_rmtree)
    monkeypatch.setattr(playwright_module.shutil, "rmtree", cleanup)

    connector = PlaywrightConnector({})
    connector.ensure_logged_in = Mock()
    connector.download_and_parse = Mock(return_value=[])
    connector.restore_profile = Mock()
    result = connector.sync("2026-08-01")

    work_dir = runtime.chromium.launch_persistent_context.call_args.args[0]
    connector.restore_profile.assert_called_once_with(work_dir)
    connector.download_and_parse.assert_called_once_with(page, "2026-08-01")
    connector.__dict__["_worker"].join(timeout=1)
    assert not Path(work_dir).exists()
    cleanup.assert_called_once_with(work_dir, ignore_errors=True)
    assert result.session is not None
    assert isinstance(result.session["profile"], str)
    context.close.assert_called_once_with()


def test_abstract_bank_steps_fail_explicitly() -> None:
    connector = PlaywrightConnector({})
    with pytest.raises(NotImplementedError):
        connector.ensure_logged_in(Mock())
    with pytest.raises(NotImplementedError):
        connector.download_and_parse(Mock(), None)


def test_default_challenge_and_cancel_are_observable() -> None:
    connector = PlaywrightConnector({})
    connector.to_worker.put(("sms", "1234"))
    assert connector.ask_sms() == "1234"
    assert connector.from_worker.get_nowait() == (
        "sms_required",
        ConnectorChallenge(
            kind="code",
            prompt="Enter the code sent by the bank.",
            can_resend=True,
        ),
    )
    connector.to_worker.put(("cancel", None))
    with pytest.raises(ConnectorError) as cancelled:
        connector.ask_sms(ConnectorChallenge(kind="captcha", prompt="Solve it"))
    assert str(cancelled.value) == "login aborted"
    connector.to_worker.put(cast("ToWorkerMessage", ("cancel", "unexpected")))
    with pytest.raises(ConnectorError) as malformed:
        connector.ask_sms()
    assert str(malformed.value) == "login aborted"


def test_profile_round_trip_prunes_every_cache_directory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
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
    for name in junk:
        directory = source / "Default" / name
        directory.mkdir(parents=True)
        (directory / "entry").write_text("cache")
    keep = source / "Default" / "Cookies"
    keep.write_text("authenticated")

    connector = PlaywrightConnector({})
    encoded = connector.archive_profile(str(source))
    with tarfile.open(fileobj=BytesIO(base64.b64decode(encoded)), mode="r:gz") as archive:
        names = set(archive.getnames())
    assert all(
        not any(part == name for part in Path(entry).parts) for name in junk for entry in names
    )

    restored = tmp_path / "restored"
    restored.mkdir()
    PlaywrightConnector({}, session={"profile": encoded}).restore_profile(str(restored))
    assert (restored / "Default" / "Cookies").read_text() == "authenticated"


def test_debug_snapshot_uses_connector_name_and_page_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MONORI_CONNECTOR_DEBUG", "1")
    page = Mock(url="https://bank.example/history")
    page.content.return_value = "<main>history</main>"
    PlaywrightConnector.shot(page, "ready")
    page.screenshot.assert_called_once_with(path="data/connector-ready.png", full_page=True)
    assert (tmp_path / "data" / "connector-ready.html").read_text() == (
        "<!-- url: https://bank.example/history -->\n<main>history</main>"
    )
    page.screenshot.side_effect = RuntimeError
    PlaywrightConnector.shot(page, "ignored")


def test_invalid_saved_profile_is_ignored_before_decoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decode = Mock(side_effect=AssertionError)
    monkeypatch.setattr(playwright_module.base64, "b64decode", decode)
    PlaywrightConnector({}, session={"profile": 42}).restore_profile(str(tmp_path))
    decode.assert_not_called()


def test_headless_accepts_only_explicit_lowercase_switches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MONORI_CONNECTOR_HEADED", raising=False)
    assert PlaywrightConnector.headless()
    for value in ("1", "true"):
        monkeypatch.setenv("MONORI_CONNECTOR_HEADED", value)
        assert not PlaywrightConnector.headless()
    monkeypatch.setenv("MONORI_CONNECTOR_HEADED", "TRUE")
    assert PlaywrightConnector.headless()


def test_optional_playwright_import_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def missing_playwright(
        name: str,
        globals_: dict[str, JsonValue] | None = None,
        locals_: dict[str, JsonValue] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> ModuleType:
        if name == "playwright.sync_api":
            raise ImportError
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", missing_playwright)
    importlib.reload(playwright_module)
    assert playwright_module.PlaywrightError is playwright_module.MissingPlaywrightError
    monkeypatch.setattr(builtins, "__import__", original_import)
    importlib.reload(playwright_module)
