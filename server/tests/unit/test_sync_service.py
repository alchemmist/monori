from threading import Barrier, Thread
from typing import override
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import monori.server.app.connectors.fake
from monori.common import JsonObject
from monori.server.app import sync_service
from monori.server.app.connectors import base
from monori.server.app.connectors.base import SmsRequiredError, SyncResult

CREDS = {"phone": "+70000000000", "password": "pw"}


@pytest.fixture
def client() -> TestClient:
    sync_service.close_all_pending()
    return TestClient(sync_service.app)


class BlockingConnector(base.Connector):
    bank = "blocking"
    kind = "blocking"
    hidden = True
    entered = Barrier(2)
    release = Barrier(2)
    closed = 0

    def __init__(
        self,
        credentials: JsonObject | None,
        session: JsonObject | None = None,
        account_ref: str | None = None,
    ) -> None:
        self.credentials = credentials or {}
        self.session = session
        self.account_ref = account_ref

    @override
    def sync(self, since: str | None = None) -> SyncResult:
        message = "code sent"
        raise SmsRequiredError(message)

    @override
    def resume_sync(self, code: str) -> SyncResult:
        type(self).entered.wait()
        type(self).release.wait()
        message = "retry"
        raise SmsRequiredError(message)

    @override
    def close(self) -> None:
        type(self).closed += 1


class RetryConnector(base.Connector):
    bank = "retry"
    kind = "retry"
    hidden = True
    closed = 0

    @override
    def sync(self, since: str | None = None) -> SyncResult:
        message = "code sent"
        raise SmsRequiredError(message)

    @override
    def resume_sync(self, code: str) -> SyncResult:
        message = "retry"
        raise SmsRequiredError(message)

    @override
    def close(self) -> None:
        type(self).closed += 1


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"ok": True}


def test_otp_flow(client: TestClient) -> None:
    r = client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    assert r.json() == {"status": "awaiting_sms", "message": sync_service.SMS_SENT}
    assert 1 in sync_service.PENDING

    r = client.post("/runs/1/sms", json={"code": "0000"})
    body = r.json()
    assert body["status"] == "done"
    assert len(body["rows"]) == 2
    assert body["session"] == {"token": "ok"}
    assert 1 not in sync_service.PENDING


def test_cached_session_skips_otp(client: TestClient) -> None:
    r = client.post(
        "/runs/1",
        json={"bank": "fake", "kind": "fake", "credentials": CREDS, "session": {"token": "ok"}},
    )
    assert r.json()["status"] == "done"


def test_connector_error_is_reported(client: TestClient) -> None:
    r = client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": {}})
    assert r.json() == {"status": "error", "message": sync_service.SYNC_FAILED}


def test_unknown_connector(client: TestClient) -> None:
    r = client.post("/runs/1", json={"bank": "nope", "kind": "nope", "credentials": CREDS})
    assert r.json()["status"] == "error"


def test_sms_without_login_is_409(client: TestClient) -> None:
    assert client.post("/runs/9/sms", json={"code": "0000"}).status_code == 409


def test_cancel_clears_pending(client: TestClient) -> None:
    client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    assert client.post("/runs/1/cancel").json() == {"cancelled": 1}
    assert client.post("/runs/1/sms", json={"code": "0000"}).status_code == 409


def test_new_run_replaces_pending_login(client: TestClient) -> None:
    client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    first = sync_service.PENDING[1]
    client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    assert sync_service.PENDING[1] is not first


def test_pending_login_expires_without_a_timing_sleep(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [10.0]
    monkeypatch.setattr(sync_service, "monotonic", lambda: now[0])
    monkeypatch.setattr(sync_service, "PENDING_TTL_SECONDS", 5)
    client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})

    now[0] = 16.0

    assert client.post("/runs/1/sms", json={"code": "0000"}).status_code == 409
    assert sync_service.PENDING == {}


def test_pending_capacity_rejects_one_above_the_limit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_service, "PENDING_CAPACITY", 1)
    assert (
        client.post(
            "/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS}
        ).status_code
        == 200
    )

    assert (
        client.post(
            "/runs/2", json={"bank": "fake", "kind": "fake", "credentials": CREDS}
        ).status_code
        == 429
    )
    assert set(sync_service.PENDING) == {1}


def test_sms_and_cancel_have_one_terminal_owner(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(base.REGISTRY, ("blocking", "blocking"), BlockingConnector)
    BlockingConnector.entered = Barrier(2)
    BlockingConnector.release = Barrier(2)
    BlockingConnector.closed = 0
    client.post("/runs/1", json={"bank": "blocking", "kind": "blocking", "credentials": CREDS})
    sms = Thread(target=lambda: client.post("/runs/1/sms", json={"code": "0000"}))
    cancel = Thread(target=lambda: client.post("/runs/1/cancel"))

    sms.start()
    BlockingConnector.entered.wait()
    cancel.start()
    BlockingConnector.release.wait()
    sms.join()
    cancel.join()

    assert sync_service.PENDING == {}
    assert BlockingConnector.closed == 1


def test_shutdown_closes_all_pending(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(base.REGISTRY, ("blocking", "blocking"), BlockingConnector)
    BlockingConnector.closed = 0
    for cid in (1, 2):
        client.post(
            f"/runs/{cid}",
            json={"bank": "blocking", "kind": "blocking", "credentials": CREDS},
        )

    sync_service.shutdown()

    assert sync_service.PENDING == {}
    assert BlockingConnector.closed == 2


def test_lifespan_runs_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    shutdown = Mock()
    monkeypatch.setattr(sync_service, "shutdown", shutdown)

    with TestClient(sync_service.app) as managed:
        assert managed.get("/health").status_code == 200

    shutdown.assert_called_once_with()


def test_ownership_helpers_reject_stale_tokens() -> None:
    connector = RetryConnector(CREDS)
    park_if_owned = vars(sync_service)["_park_if_owned"]
    release_if_owned = vars(sync_service)["_release_if_owned"]

    assert park_if_owned(1, sync_service.RunToken(), connector) is False
    assert release_if_owned(1, sync_service.RunToken()) is False


@pytest.mark.parametrize(
    "body",
    [
        {"bank": "fake", "kind": "fake", "credentials": {}},
        {
            "bank": "fake",
            "kind": "fake",
            "credentials": CREDS,
            "session": {"token": "ok"},
        },
    ],
)
def test_cancelled_start_completion_is_409(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    body: JsonObject,
) -> None:
    monkeypatch.setattr(sync_service, "_release_if_owned", lambda *_: False)

    response = client.post("/runs/1", json=body)

    assert response.status_code == 409
    assert response.json() == {"detail": "login was cancelled or superseded"}


def test_cancelled_start_cannot_repark_after_sms(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_service, "_park_if_owned", lambda *_: False)

    response = client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    assert response.status_code == 409


@pytest.mark.parametrize("code", ["bad", "0000"])
def test_cancelled_sms_completion_is_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    monkeypatch.setattr(sync_service, "_release_if_owned", lambda *_: False)

    assert client.post("/runs/1/sms", json={"code": code}).status_code == 409


def test_cancelled_sms_cannot_repark(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(base.REGISTRY, ("retry", "retry"), RetryConnector)
    client.post("/runs/1", json={"bank": "retry", "kind": "retry", "credentials": CREDS})
    monkeypatch.setattr(sync_service, "_park_if_owned", lambda *_: False)

    assert client.post("/runs/1/sms", json={"code": "again"}).status_code == 409


@pytest.mark.parametrize("path", ["/runs/1/sms", "/runs/9/cancel"])
def test_expired_connectors_are_closed_by_terminal_requests(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    monkeypatch.setitem(base.REGISTRY, ("retry", "retry"), RetryConnector)
    RetryConnector.closed = 0
    connector = RetryConnector(CREDS)
    if path.endswith("/sms"):
        client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    sync_service.PENDING[2] = sync_service.PendingSession(
        sync_service.RunToken(), connector, expires_at=0
    )

    response = client.post(path, json={"code": "0000"})

    assert response.status_code == 200
    assert RetryConnector.closed == 1
