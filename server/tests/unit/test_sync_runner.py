import httpx
import pytest
from fastapi.testclient import TestClient

import app.connectors.fake  # noqa: F401  (registers the FakeConnector)
from app import sync_service
from app.connectors.base import ConnectorError, SmsRequired
from app.sync_runner import LocalRunner, NoPendingLogin, RemoteRunner, get_runner

CREDS = {"phone": "+70000000000", "password": "pw"}


def remote_runner():
    service = TestClient(sync_service.app)

    def handler(request):
        resp = service.request(
            request.method,
            request.url.path,
            content=request.content,
            headers={"content-type": "application/json"},
        )
        return httpx.Response(resp.status_code, content=resp.content)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    return RemoteRunner("http://sync", client=client)


@pytest.fixture(params=[LocalRunner, remote_runner])
def runner(request):
    sync_service.PENDING.clear()
    return request.param()


def test_otp_flow(runner):
    with pytest.raises(SmsRequired):
        runner.start(1, "fake", "fake", CREDS, None, None)
    result = runner.resume(1, "0000")
    assert len(result.rows) == 2
    assert result.session == {"token": "ok"}


def test_cached_session_skips_otp(runner):
    result = runner.start(1, "fake", "fake", CREDS, {"token": "ok"}, None)
    assert len(result.rows) == 2


def test_connector_error(runner):
    with pytest.raises(ConnectorError, match="missing phone"):
        runner.start(1, "fake", "fake", {}, None, None)


def test_resume_without_login(runner):
    with pytest.raises(NoPendingLogin):
        runner.resume(7, "0000")


def test_cancel_drops_pending(runner):
    with pytest.raises(SmsRequired):
        runner.start(1, "fake", "fake", CREDS, None, None)
    runner.cancel(1)
    with pytest.raises(NoPendingLogin):
        runner.resume(1, "0000")


def test_remote_maps_transport_failure_to_connector_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    r = RemoteRunner("http://sync", client=client)
    with pytest.raises(ConnectorError, match="sync service unavailable"):
        r.start(1, "fake", "fake", CREDS, None, None)


@pytest.mark.parametrize("content", [b"not json", b"[1, 2]"])
def test_remote_maps_malformed_response_to_connector_error(content):
    def handler(request):
        return httpx.Response(200, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    r = RemoteRunner("http://sync", client=client)
    with pytest.raises(ConnectorError, match="invalid response"):
        r.start(1, "fake", "fake", CREDS, None, None)


class ClosableConnector:
    bank = "closable"
    kind = "closable"
    hidden = True
    closed = 0

    def __init__(self, credentials, session=None):
        self.credentials = credentials
        self.session = session

    def sync(self, since=None):
        raise SmsRequired("code sent")

    def resume_sync(self, code):
        raise ConnectorError("bad code")

    def close(self):
        type(self).closed += 1


def test_failed_resume_closes_connector(monkeypatch):
    from app.connectors import base

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


def test_service_failed_resume_closes_connector(monkeypatch):
    from app.connectors import base

    monkeypatch.setitem(base.REGISTRY, ("closable", "closable"), ClosableConnector)
    ClosableConnector.closed = 0
    sync_service.PENDING.clear()
    service = TestClient(sync_service.app)
    service.post("/runs/1", json={"bank": "closable", "kind": "closable", "credentials": CREDS})
    r = service.post("/runs/1/sms", json={"code": "0000"})
    assert r.json()["status"] == "error"
    assert ClosableConnector.closed == 1
    assert 1 not in sync_service.PENDING


def test_get_runner_selects_by_env(monkeypatch):
    import app.sync_runner as sr

    monkeypatch.setattr(sr, "_runner", None)
    monkeypatch.delenv("MONORI_SYNC_URL", raising=False)
    assert isinstance(get_runner(), LocalRunner)

    monkeypatch.setattr(sr, "_runner", None)
    monkeypatch.setenv("MONORI_SYNC_URL", "http://sync:8010")
    assert isinstance(get_runner(), RemoteRunner)

    monkeypatch.setattr(sr, "_runner", None)
