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


def test_get_runner_selects_by_env(monkeypatch):
    import app.sync_runner as sr

    monkeypatch.setattr(sr, "_runner", None)
    monkeypatch.delenv("MONORI_SYNC_URL", raising=False)
    assert isinstance(get_runner(), LocalRunner)

    monkeypatch.setattr(sr, "_runner", None)
    monkeypatch.setenv("MONORI_SYNC_URL", "http://sync:8010")
    assert isinstance(get_runner(), RemoteRunner)

    monkeypatch.setattr(sr, "_runner", None)
