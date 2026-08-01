from dataclasses import dataclass

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

import app.connectors.fake  # noqa: F401  (registers the FakeConnector)
from app import sync_service
from app.connectors import base
from app.connectors.base import ConnectorError, JsonObject, SmsRequired, SyncResult
from app.sync_runner import LocalRunner, NoPendingLogin, RemoteRunner, get_runner

CREDS: JsonObject = {"phone": "+70000000000", "password": "pw"}
type Runner = LocalRunner | RemoteRunner


def remote_runner() -> RemoteRunner:
    service = TestClient(sync_service.app)

    def handler(request: httpx.Request) -> httpx.Response:
        resp = service.request(
            request.method,
            request.url.path,
            content=request.content,
            headers={"content-type": "application/json"},
        )
        return httpx.Response(resp.status_code, content=resp.content)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    return RemoteRunner("http://sync", client=client)


@pytest.fixture(params=["local", "remote"])
def runner(request: pytest.FixtureRequest) -> Runner:
    sync_service.PENDING.clear()
    if request.param == "local":
        return LocalRunner()
    return remote_runner()


def test_otp_flow(runner: Runner) -> None:
    with pytest.raises(SmsRequired):
        runner.start(1, "fake", "fake", CREDS, None, None)
    result = runner.resume(1, "0000")
    assert len(result.rows) == 2
    assert result.session == {"token": "ok"}


def test_cached_session_skips_otp(runner: Runner) -> None:
    result = runner.start(1, "fake", "fake", CREDS, {"token": "ok"}, None)
    assert len(result.rows) == 2


def test_connector_error(runner: Runner) -> None:
    expected = sync_service.SYNC_FAILED if isinstance(runner, RemoteRunner) else "missing phone"
    with pytest.raises(ConnectorError) as ei:
        runner.start(1, "fake", "fake", {}, None, None)
    assert expected in str(ei.value)


def test_resume_without_login(runner: Runner) -> None:
    with pytest.raises(NoPendingLogin):
        runner.resume(7, "0000")


def test_cancel_drops_pending(runner: Runner) -> None:
    with pytest.raises(SmsRequired):
        runner.start(1, "fake", "fake", CREDS, None, None)
    runner.cancel(1)
    with pytest.raises(NoPendingLogin):
        runner.resume(1, "0000")


def test_remote_maps_transport_failure_to_connector_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    r = RemoteRunner("http://sync", client=client)
    with pytest.raises(ConnectorError, match="sync service unavailable"):
        r.start(1, "fake", "fake", CREDS, None, None)


@pytest.mark.parametrize("content", [b"not json", b"[1, 2]"])
def test_remote_maps_malformed_response_to_connector_error(content: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    r = RemoteRunner("http://sync", client=client)
    with pytest.raises(ConnectorError, match="invalid response"):
        r.start(1, "fake", "fake", CREDS, None, None)


class ClosableConnector:
    bank = "closable"
    kind = "closable"
    hidden = True
    closed: int = 0

    def __init__(
        self,
        credentials: JsonObject | None,
        session: JsonObject | None = None,
        account_ref: str | None = None,
    ) -> None:
        self.account_ref = account_ref
        self.credentials = credentials or {}
        self.session = session

    def sync(self, since: str | None = None) -> SyncResult:
        raise SmsRequired("code sent")

    def resume_sync(self, code: str) -> SyncResult:
        raise ConnectorError("bad code")

    def close(self) -> None:
        type(self).closed += 1


def test_failed_resume_closes_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(base.REGISTRY, ("closable", "closable"), ClosableConnector)
    ClosableConnector.closed = 0
    runner = LocalRunner()
    with pytest.raises(SmsRequired):
        runner.start(1, "closable", "closable", CREDS, None, None)
    with pytest.raises(ConnectorError, match="bad code"):
        runner.resume(1, "0000")
    assert ClosableConnector.closed == 1
    with pytest.raises(NoPendingLogin):
        runner.resume(1, "0000")


def test_service_failed_resume_closes_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(base.REGISTRY, ("closable", "closable"), ClosableConnector)
    ClosableConnector.closed = 0
    sync_service.PENDING.clear()
    service = TestClient(sync_service.app)
    service.post("/runs/1", json={"bank": "closable", "kind": "closable", "credentials": CREDS})
    r = service.post("/runs/1/sms", json={"code": "0000"})
    assert r.json()["status"] == "error"
    assert ClosableConnector.closed == 1
    assert 1 not in sync_service.PENDING


class RecordingConnector:
    bank = "recording"
    kind = "recording"
    hidden = True
    last_since: str | None = None

    def __init__(
        self,
        credentials: JsonObject | None,
        session: JsonObject | None = None,
        account_ref: str | None = None,
    ) -> None:
        self.account_ref = account_ref
        self.credentials = credentials or {}
        self.session = session

    def sync(self, since: str | None = None) -> SyncResult:
        type(self).last_since = since
        return SyncResult([], session=None)

    def resume_sync(self, code: str) -> SyncResult:
        raise ConnectorError("no login in progress")

    def close(self) -> None:
        return None


class RetryOtpConnector:
    bank = "retryotp"
    kind = "retryotp"
    hidden = True
    closed: int = 0

    def __init__(
        self,
        credentials: JsonObject | None,
        session: JsonObject | None = None,
        account_ref: str | None = None,
    ) -> None:
        self.account_ref = account_ref
        self.credentials = credentials or {}
        self.session = session

    def sync(self, since: str | None = None) -> SyncResult:
        raise SmsRequired("code sent")

    def resume_sync(self, code: str) -> SyncResult:
        if code != "4242":
            raise SmsRequired("the bank rejected the code — check it and try again")
        return SyncResult([], session=None)

    def close(self) -> None:
        type(self).closed += 1


class FailingCloseConnector(ClosableConnector):
    bank = "failclose"
    kind = "failclose"

    def close(self) -> None:
        type(self).closed += 1
        raise RuntimeError("close blew up")


def test_since_is_passed_through(runner: Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(base.REGISTRY, ("recording", "recording"), RecordingConnector)
    RecordingConnector.last_since = None
    runner.start(1, "recording", "recording", CREDS, None, "2026-01-01")
    assert RecordingConnector.last_since == "2026-01-01"


def test_new_start_closes_previous_pending(runner: Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(base.REGISTRY, ("closable", "closable"), ClosableConnector)
    ClosableConnector.closed = 0
    with pytest.raises(SmsRequired):
        runner.start(1, "closable", "closable", CREDS, None, None)
    with pytest.raises(SmsRequired):
        runner.start(1, "closable", "closable", CREDS, None, None)
    assert ClosableConnector.closed == 1


def test_cancel_closes_pending_connector(runner: Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(base.REGISTRY, ("closable", "closable"), ClosableConnector)
    ClosableConnector.closed = 0
    with pytest.raises(SmsRequired):
        runner.start(1, "closable", "closable", CREDS, None, None)
    runner.cancel(1)
    assert ClosableConnector.closed == 1


def test_failing_close_never_masks_the_flow(
    runner: Runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(base.REGISTRY, ("failclose", "failclose"), FailingCloseConnector)
    FailingCloseConnector.closed = 0
    with pytest.raises(SmsRequired):
        runner.start(1, "failclose", "failclose", CREDS, None, None)
    runner.cancel(1)
    assert FailingCloseConnector.closed == 1
    with pytest.raises(SmsRequired):
        runner.start(2, "failclose", "failclose", CREDS, None, None)
    expected = sync_service.SYNC_FAILED if isinstance(runner, RemoteRunner) else "bad code"
    with pytest.raises(ConnectorError) as ei:
        runner.resume(2, "0000")
    assert expected in str(ei.value)
    assert FailingCloseConnector.closed == 2


def test_rejected_code_keeps_login_alive(runner: Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(base.REGISTRY, ("retryotp", "retryotp"), RetryOtpConnector)
    RetryOtpConnector.closed = 0
    with pytest.raises(SmsRequired):
        runner.start(1, "retryotp", "retryotp", CREDS, None, None)
    with pytest.raises(SmsRequired) as ei:
        runner.resume(1, "0000")
    expected = (
        sync_service.CODE_REJECTED
        if isinstance(runner, RemoteRunner)
        else "the bank rejected the code — check it and try again"
    )
    assert str(ei.value) == expected
    assert RetryOtpConnector.closed == 0
    result = runner.resume(1, "4242")
    assert result.rows == []


def test_remote_error_messages_are_exact() -> None:
    responses: dict[bytes, str] = {
        b"not json": "sync service returned an invalid response",
        b"[1, 2]": "sync service returned an invalid response",
        b'{"status": "error"}': "sync failed",
    }
    for content, expected in responses.items():

        def handler(request: httpx.Request, content: bytes = content) -> httpx.Response:
            return httpx.Response(200, content=content)

        client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
        r = RemoteRunner("http://sync", client=client)
        with pytest.raises(ConnectorError) as ei:
            r.start(1, "fake", "fake", CREDS, None, None)
        assert str(ei.value) == expected


def test_remote_awaiting_sms_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "awaiting_sms"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    r = RemoteRunner("http://sync", client=client)
    with pytest.raises(SmsRequired) as ei:
        r.start(1, "fake", "fake", CREDS, None, None)
    assert str(ei.value) == "code sent"


def test_remote_resume_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    r = RemoteRunner("http://sync", client=client)
    with pytest.raises(ConnectorError, match="sync service unavailable"):
        r.resume(1, "0000")


@dataclass
class CapturedRequest:
    path: str = ""
    timeout: dict[str, float] | None = None


TIMEOUT_ADAPTER: TypeAdapter[dict[str, float]] = TypeAdapter(dict[str, float])


def test_remote_cancel_uses_short_timeout() -> None:
    captured = CapturedRequest()

    def handler(request: httpx.Request) -> httpx.Response:
        captured.path = request.url.path
        captured.timeout = TIMEOUT_ADAPTER.validate_python(request.extensions.get("timeout"))
        return httpx.Response(200, json={"cancelled": 5})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    RemoteRunner("http://sync", client=client).cancel(5)
    assert captured.path == "/runs/5/cancel"
    assert captured.timeout == {"connect": 2.0, "read": 5.0, "write": 5.0, "pool": 5.0}


def test_remote_cancel_swallows_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    RemoteRunner("http://sync", client=client).cancel(5)


def test_get_runner_selects_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.sync_runner as sr

    monkeypatch.setattr(sr, "_runner", None)
    monkeypatch.delenv("MONORI_SYNC_URL", raising=False)
    assert isinstance(get_runner(), LocalRunner)

    monkeypatch.setattr(sr, "_runner", None)
    monkeypatch.setenv("MONORI_SYNC_URL", "http://sync:8010")
    assert isinstance(get_runner(), RemoteRunner)

    monkeypatch.setattr(sr, "_runner", None)
