import httpx
import pytest
from fastapi.testclient import TestClient

import app.connectors.fake  # noqa: F401  (registers the FakeConnector)
from app import sync_service
from app.connectors import base
from app.connectors.base import ConnectorError, SmsRequired, SyncResult
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

    def __init__(self, credentials, session=None, account_ref=None):
        self.account_ref = account_ref
        self.credentials = credentials
        self.session = session

    def sync(self, since=None):
        raise SmsRequired("code sent")

    def resume_sync(self, code):
        raise ConnectorError("bad code")

    def close(self):
        type(self).closed += 1


def test_failed_resume_closes_connector(monkeypatch):
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
    last_since = None

    def __init__(self, credentials, session=None, account_ref=None):
        self.account_ref = account_ref
        self.credentials = credentials
        self.session = session

    def sync(self, since=None):
        type(self).last_since = since
        return SyncResult([], session=None)

    def resume_sync(self, code):
        raise ConnectorError("no login in progress")

    def close(self):
        pass


class RetryOtpConnector:
    bank = "retryotp"
    kind = "retryotp"
    hidden = True
    closed = 0

    def __init__(self, credentials, session=None, account_ref=None):
        self.account_ref = account_ref
        self.credentials = credentials
        self.session = session

    def sync(self, since=None):
        raise SmsRequired("code sent")

    def resume_sync(self, code):
        if code != "4242":
            raise SmsRequired("the bank rejected the code — check it and try again")
        return SyncResult([], session=None)

    def close(self):
        type(self).closed += 1


class FailingCloseConnector(ClosableConnector):
    bank = "failclose"
    kind = "failclose"

    def close(self):
        type(self).closed += 1
        raise RuntimeError("close blew up")


def test_since_is_passed_through(runner, monkeypatch):
    monkeypatch.setitem(base.REGISTRY, ("recording", "recording"), RecordingConnector)
    RecordingConnector.last_since = None
    runner.start(1, "recording", "recording", CREDS, None, "2026-01-01")
    assert RecordingConnector.last_since == "2026-01-01"


def test_new_start_closes_previous_pending(runner, monkeypatch):
    monkeypatch.setitem(base.REGISTRY, ("closable", "closable"), ClosableConnector)
    ClosableConnector.closed = 0
    with pytest.raises(SmsRequired):
        runner.start(1, "closable", "closable", CREDS, None, None)
    with pytest.raises(SmsRequired):
        runner.start(1, "closable", "closable", CREDS, None, None)
    assert ClosableConnector.closed == 1


def test_cancel_closes_pending_connector(runner, monkeypatch):
    monkeypatch.setitem(base.REGISTRY, ("closable", "closable"), ClosableConnector)
    ClosableConnector.closed = 0
    with pytest.raises(SmsRequired):
        runner.start(1, "closable", "closable", CREDS, None, None)
    runner.cancel(1)
    assert ClosableConnector.closed == 1


def test_failing_close_never_masks_the_flow(runner, monkeypatch):
    monkeypatch.setitem(base.REGISTRY, ("failclose", "failclose"), FailingCloseConnector)
    FailingCloseConnector.closed = 0
    with pytest.raises(SmsRequired):
        runner.start(1, "failclose", "failclose", CREDS, None, None)
    runner.cancel(1)
    assert FailingCloseConnector.closed == 1
    with pytest.raises(SmsRequired):
        runner.start(2, "failclose", "failclose", CREDS, None, None)
    with pytest.raises(ConnectorError, match="bad code"):
        runner.resume(2, "0000")
    assert FailingCloseConnector.closed == 2


def test_rejected_code_keeps_login_alive(runner, monkeypatch):
    monkeypatch.setitem(base.REGISTRY, ("retryotp", "retryotp"), RetryOtpConnector)
    RetryOtpConnector.closed = 0
    with pytest.raises(SmsRequired):
        runner.start(1, "retryotp", "retryotp", CREDS, None, None)
    with pytest.raises(SmsRequired) as ei:
        runner.resume(1, "0000")
    assert str(ei.value) == "the bank rejected the code — check it and try again"
    assert RetryOtpConnector.closed == 0
    result = runner.resume(1, "4242")
    assert result.rows == []


def test_remote_error_messages_are_exact():
    responses = {
        b"not json": "sync service returned an invalid response",
        b"[1, 2]": "sync service returned an invalid response",
        b'{"status": "error"}': "sync failed",
    }
    for content, expected in responses.items():

        def handler(request, content=content):
            return httpx.Response(200, content=content)

        client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
        r = RemoteRunner("http://sync", client=client)
        with pytest.raises(ConnectorError) as ei:
            r.start(1, "fake", "fake", CREDS, None, None)
        assert str(ei.value) == expected


def test_remote_awaiting_sms_message():
    def handler(request):
        return httpx.Response(200, json={"status": "awaiting_sms"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    r = RemoteRunner("http://sync", client=client)
    with pytest.raises(SmsRequired) as ei:
        r.start(1, "fake", "fake", CREDS, None, None)
    assert str(ei.value) == "code sent"


def test_remote_resume_transport_failure():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    r = RemoteRunner("http://sync", client=client)
    with pytest.raises(ConnectorError, match="sync service unavailable"):
        r.resume(1, "0000")


def test_remote_cancel_uses_short_timeout():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["timeout"] = request.extensions.get("timeout")
        return httpx.Response(200, json={"cancelled": 5})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    RemoteRunner("http://sync", client=client).cancel(5)
    assert captured["path"] == "/runs/5/cancel"
    assert captured["timeout"] == {"connect": 2.0, "read": 5.0, "write": 5.0, "pool": 5.0}


def test_remote_cancel_swallows_transport_failure():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://sync")
    RemoteRunner("http://sync", client=client).cancel(5)


def test_get_runner_selects_by_env(monkeypatch):
    import app.sync_runner as sr

    monkeypatch.setattr(sr, "_runner", None)
    monkeypatch.delenv("MONORI_SYNC_URL", raising=False)
    assert isinstance(get_runner(), LocalRunner)

    monkeypatch.setattr(sr, "_runner", None)
    monkeypatch.setenv("MONORI_SYNC_URL", "http://sync:8010")
    assert isinstance(get_runner(), RemoteRunner)

    monkeypatch.setattr(sr, "_runner", None)
