import pytest
from fastapi.testclient import TestClient

import app.connectors.fake  # noqa: F401  (registers the FakeConnector)
from app import sync_service

CREDS = {"phone": "+70000000000", "password": "pw"}


@pytest.fixture()
def client():
    sync_service.PENDING.clear()
    return TestClient(sync_service.app)


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_otp_flow(client):
    r = client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    assert r.json() == {"status": "awaiting_sms"}
    assert 1 in sync_service.PENDING

    r = client.post("/runs/1/sms", json={"code": "0000"})
    body = r.json()
    assert body["status"] == "done"
    assert len(body["rows"]) == 2
    assert body["session"] == {"token": "ok"}
    assert 1 not in sync_service.PENDING


def test_cached_session_skips_otp(client):
    r = client.post(
        "/runs/1",
        json={"bank": "fake", "kind": "fake", "credentials": CREDS, "session": {"token": "ok"}},
    )
    assert r.json()["status"] == "done"


def test_connector_error_is_reported(client):
    r = client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": {}})
    assert r.json() == {"status": "error", "message": "missing phone"}


def test_unknown_connector(client):
    r = client.post("/runs/1", json={"bank": "nope", "kind": "nope", "credentials": CREDS})
    assert r.json()["status"] == "error"


def test_sms_without_login_is_409(client):
    assert client.post("/runs/9/sms", json={"code": "0000"}).status_code == 409


def test_cancel_clears_pending(client):
    client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    assert client.post("/runs/1/cancel").json() == {"cancelled": 1}
    assert client.post("/runs/1/sms", json={"code": "0000"}).status_code == 409


def test_new_run_replaces_pending_login(client):
    client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    first = sync_service.PENDING[1]
    client.post("/runs/1", json={"bank": "fake", "kind": "fake", "credentials": CREDS})
    assert sync_service.PENDING[1] is not first
