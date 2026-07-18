import pytest
from cryptography.fernet import Fernet

import app.connectors.fake  # noqa: F401  (registers the FakeConnector)


@pytest.fixture()
def keyed(monkeypatch):
    monkeypatch.setenv("MONORI_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _connect(client, account_id):
    return client.post(
        "/api/connections",
        json={
            "accountId": account_id,
            "bank": "fake",
            "kind": "fake",
            "credentials": {"phone": "+70000000000", "password": "pw"},
        },
    )


def test_create_requires_encryption_key(api, client):
    r = _connect(client, api.default_account())
    assert r.status_code == 400
    assert "MONORI_ENCRYPTION_KEY" in r.json()["detail"]


def test_create_rejects_unknown_bank(api, client, keyed):
    r = client.post(
        "/api/connections",
        json={
            "accountId": api.default_account(),
            "bank": "nope",
            "kind": "nope",
            "credentials": {"phone": "+7", "password": "p"},
        },
    )
    assert r.status_code == 400


def test_connection_appears_in_snapshot_without_secrets(api, client, keyed):
    r = _connect(client, api.default_account())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "disconnected"
    assert body["hasCredentials"] is True
    assert "credentials" not in body and "credentials_encrypted" not in body
    conns = api.snapshot()["connections"]
    assert len(conns) == 1
    assert conns[0]["bank"] == "fake"


def test_two_phase_sync_then_incremental_dedup(api, client, keyed):
    acct = api.default_account()
    cid = _connect(client, acct).json()["id"]

    # first sync stops at the OTP step
    r = client.post(f"/api/connections/{cid}/sync")
    assert r.json()["status"] == "awaiting_sms"
    assert api.snapshot()["connections"][0]["status"] == "awaiting_sms"

    # a wrong code fails and clears the pending login
    client.post(f"/api/connections/{cid}/sync")
    r = client.post(f"/api/connections/{cid}/sms", json={"code": "9999"})
    assert r.status_code == 502
    assert api.snapshot()["connections"][0]["status"] == "error"

    # a fresh attempt with the right code lands the rows as a sync batch
    client.post(f"/api/connections/{cid}/sync")
    r = client.post(f"/api/connections/{cid}/sms", json={"code": "0000"})
    body = r.json()
    assert body["status"] == "connected"
    assert body["inserted"] == 2
    assert body["skipped"] == 0
    assert body["dateFrom"] == "2026-02-01T09:00:00"

    snap = api.snapshot()
    synced = [t for t in snap["transactions"] if t["source"] == "sync"]
    assert len(synced) == 2
    assert all(t["accountId"] == acct for t in synced)
    assert snap["connections"][0]["status"] == "connected"
    assert snap["connections"][0]["lastSync"] is not None

    # second sync reuses the cached session (no OTP) and dedups everything
    r = client.post(f"/api/connections/{cid}/sync")
    body = r.json()
    assert body["status"] == "connected"
    assert body["inserted"] == 0
    assert body["skipped"] == 2


def test_sms_without_pending_login_conflicts(api, client, keyed):
    cid = _connect(client, api.default_account()).json()["id"]
    r = client.post(f"/api/connections/{cid}/sms", json={"code": "0000"})
    assert r.status_code == 409


def test_delete_connection(api, client, keyed):
    cid = _connect(client, api.default_account()).json()["id"]
    assert client.delete(f"/api/connections/{cid}").status_code == 200
    assert api.snapshot()["connections"] == []
