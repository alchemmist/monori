import pytest
from cryptography.fernet import Fernet

import app.connectors.fake  # noqa: F401  (registers the FakeConnector)
from app.connectors import base
from app.connectors.base import SmsRequired, SyncResult


@pytest.fixture()
def keyed(monkeypatch):
    monkeypatch.setenv("MONORI_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _connect(client, account_id):
    r = client.post(
        "/api/connections",
        json={
            "bank": "fake",
            "kind": "fake",
            "credentials": {"phone": "+70000000000", "password": "pw"},
        },
    )
    if r.status_code == 200 and account_id is not None:
        link = client.patch(f"/api/accounts/{account_id}", json={"connectionId": r.json()["id"]})
        assert link.status_code == 200, link.text
    return r


def test_create_auto_provisions_encryption_key(api, client, monkeypatch):
    # with no MONORI_ENCRYPTION_KEY set, the key is generated and persisted on
    # demand, so bank connections work out of the box
    monkeypatch.delenv("MONORI_ENCRYPTION_KEY", raising=False)
    r = _connect(client, api.default_account())
    assert r.status_code == 200, r.text


def test_create_rejects_unknown_bank(api, client, keyed):
    r = client.post(
        "/api/connections",
        json={
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
    # categories so the synced rows get auto-categorized in _finish
    inc = api.group("Income", kind="income")
    exp = api.group("Spending", kind="expense")
    salary_cat = api.category("Salary", inc, keywords="salary")
    food_cat = api.category("Food", exp, keywords="lenta")
    cid = _connect(client, acct).json()["id"]

    # first sync stops at the OTP step
    r = client.post(f"/api/connections/{cid}/sync")
    assert r.json()["status"] == "awaiting_sms"
    assert api.snapshot()["connections"][0]["status"] == "awaiting_sms"

    # a wrong code resumes the same pending login, fails, and clears it
    r = client.post(f"/api/connections/{cid}/sms", json={"code": "9999"})
    assert r.status_code == 502
    assert api.snapshot()["connections"][0]["status"] == "error"
    # the pending login is now gone: a second code submission conflicts
    assert client.post(f"/api/connections/{cid}/sms", json={"code": "0000"}).status_code == 409

    # a fresh attempt with the right code lands the rows as a sync batch
    client.post(f"/api/connections/{cid}/sync")
    r = client.post(f"/api/connections/{cid}/sms", json={"code": "0000"})
    body = r.json()
    assert body["status"] == "connected"
    assert body["inserted"] == 2
    assert body["skipped"] == 0
    assert body["dateFrom"] == "2026-02-01T09:00:00"
    assert body["dateTo"] == "2026-02-02T12:30:00"
    assert body["accounts"][0]["batchId"] is not None

    snap = api.snapshot()
    synced = [t for t in snap["transactions"] if t["source"] == "sync"]
    assert len(synced) == 2
    assert all(t["accountId"] == acct for t in synced)
    # the sync ran the rows through categorization
    by_desc = {t["description"]: t for t in synced}
    assert by_desc["Lenta"]["categoryId"] == food_cat
    assert by_desc["Salary"]["categoryId"] == salary_cat
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


def test_cancel_clears_pending_login(api, client, keyed):
    cid = _connect(client, api.default_account()).json()["id"]
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "awaiting_sms"
    assert client.post(f"/api/connections/{cid}/cancel").status_code == 200
    assert api.snapshot()["connections"][0]["status"] == "disconnected"
    # nothing is parked anymore
    assert client.post(f"/api/connections/{cid}/sms", json={"code": "0000"}).status_code == 409


def test_resync_replaces_pending_login(api, client, keyed):
    cid = _connect(client, api.default_account()).json()["id"]
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "awaiting_sms"
    # a second sync closes the first pending login and parks a fresh one, which
    # the correct code then completes
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "awaiting_sms"
    assert client.post(f"/api/connections/{cid}/sms", json={"code": "0000"}).json()["status"] == (
        "connected"
    )


def test_delete_connection(api, client, keyed):
    cid = _connect(client, api.default_account()).json()["id"]
    assert client.delete(f"/api/connections/{cid}").status_code == 200
    assert api.snapshot()["connections"] == []


class RetryOtpConnector:
    bank = "retryotp"
    kind = "retryotp"
    hidden = True

    def __init__(self, credentials, session=None, account_ref=None):
        self.credentials = credentials
        self.session = session
        self.account_ref = account_ref

    def sync(self, since=None):
        raise SmsRequired("code sent")

    def resume_sync(self, code):
        if code != "4242":
            raise SmsRequired("the bank rejected the code — check it and try again")
        return SyncResult([], session=None)

    def close(self):
        pass


def test_rejected_code_stays_awaiting(api, client, keyed, monkeypatch):
    monkeypatch.setitem(base.REGISTRY, ("retryotp", "retryotp"), RetryOtpConnector)
    cid = client.post(
        "/api/connections",
        json={
            "bank": "retryotp",
            "kind": "retryotp",
            "credentials": {"phone": "+70000000000", "password": "pw"},
        },
    ).json()["id"]
    r = client.patch(f"/api/accounts/{api.default_account()}", json={"connectionId": cid})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "awaiting_sms"

    r = client.post(f"/api/connections/{cid}/sms", json={"code": "1111"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "awaiting_sms"
    assert body["message"] == "the bank rejected the code — check it and try again"
    assert api.snapshot()["connections"][0]["status"] == "awaiting_sms"

    assert client.post(f"/api/connections/{cid}/sms", json={"code": "4242"}).json()["status"] == (
        "connected"
    )


def test_available_lists_connectors_with_params(client):
    r = client.get("/api/connections/available")
    assert r.status_code == 200
    banks = {c["bank"]: c for c in r.json()}
    assert "fake" not in banks
    tbank = banks["tbank"]
    assert tbank["label"] == "T-Bank (browser sync)"
    assert {p["name"] for p in tbank["connectionParams"]} == {"phone", "password"}
    assert [p["name"] for p in tbank["accountParams"]] == ["account"]


def test_one_connection_syncs_multiple_accounts(api, client, keyed):
    a1 = api.default_account()
    a2 = api.account("Savings")
    cid = _connect(client, a1).json()["id"]
    r = client.patch(f"/api/accounts/{a2}", json={"connectionId": cid, "bankRef": " 8121254731 "})
    assert r.status_code == 200
    snap = api.snapshot()
    linked = {a["id"]: a for a in snap["accounts"]}
    assert linked[a1]["connectionId"] == cid
    assert linked[a2]["connectionId"] == cid
    assert linked[a2]["bankRef"] == "8121254731"

    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "awaiting_sms"
    body = client.post(f"/api/connections/{cid}/sms", json={"code": "0000"}).json()
    assert body["status"] == "connected"
    assert len(body["accounts"]) == 2
    assert {r["accountId"] for r in body["accounts"]} == {a1, a2}
    assert body["inserted"] == 4
    per_account = {r["accountId"]: r for r in body["accounts"]}
    assert per_account[a1]["inserted"] == 2
    assert per_account[a2]["inserted"] == 2
    assert per_account[a1]["batchId"] != per_account[a2]["batchId"]
    txs = api.snapshot()["transactions"]
    assert len([t for t in txs if t["accountId"] == a1]) == 2
    assert len([t for t in txs if t["accountId"] == a2]) == 2


def test_sync_requires_a_linked_account(api, client, keyed):
    r = client.post(
        "/api/connections",
        json={
            "bank": "fake",
            "kind": "fake",
            "credentials": {"phone": "+70000000000", "password": "pw"},
        },
    )
    cid = r.json()["id"]
    r = client.post(f"/api/connections/{cid}/sync")
    assert r.status_code == 400
    assert "linked" in r.json()["detail"]


def test_delete_connection_unlinks_accounts(api, client, keyed):
    a1 = api.default_account()
    cid = _connect(client, a1).json()["id"]
    assert api.snapshot()["accounts"][0]["connectionId"] == cid
    client.delete(f"/api/connections/{cid}")
    snap = api.snapshot()
    assert snap["connections"] == []
    assert snap["accounts"][0]["connectionId"] is None


def test_unlink_account_via_patch(api, client, keyed):
    a1 = api.default_account()
    _connect(client, a1)
    r = client.patch(f"/api/accounts/{a1}", json={"connectionId": 0})
    assert r.status_code == 200
    assert api.snapshot()["accounts"][0]["connectionId"] is None
    assert len(api.snapshot()["connections"]) == 1


def test_link_rejects_unknown_connection(api, client, keyed):
    r = client.patch(f"/api/accounts/{api.default_account()}", json={"connectionId": 999})
    assert r.status_code == 400


def test_missing_required_credentials_rejected(api, client, keyed):
    r = client.post(
        "/api/connections",
        json={"bank": "tbank", "kind": "playwright", "credentials": {"phone": "+7"}},
    )
    assert r.status_code == 400
    assert "password" in r.json()["detail"]


class SinceRecorder:
    bank = "sincer"
    kind = "sincer"
    hidden = True
    calls = []

    def __init__(self, credentials, session=None, account_ref=None):
        self.credentials = credentials
        self.session = session
        self.account_ref = account_ref

    def sync(self, since=None):
        SinceRecorder.calls.append((self.account_ref, since))
        return SyncResult([], session={"token": "ok"})

    def close(self):
        pass


def test_newly_linked_account_gets_a_full_pull(api, client, keyed, monkeypatch):
    monkeypatch.setitem(base.REGISTRY, ("sincer", "sincer"), SinceRecorder)
    SinceRecorder.calls = []
    a1 = api.default_account()
    cid = client.post(
        "/api/connections",
        json={"bank": "sincer", "kind": "sincer", "credentials": {"phone": "+7"}},
    ).json()["id"]
    client.patch(f"/api/accounts/{a1}", json={"connectionId": cid, "bankRef": "ref1"})
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "connected"
    assert SinceRecorder.calls == [("ref1", None)]

    a2 = api.account("Second")
    client.patch(f"/api/accounts/{a2}", json={"connectionId": cid, "bankRef": "ref2"})
    SinceRecorder.calls = []
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "connected"
    refs = dict(SinceRecorder.calls)
    assert refs["ref1"] is not None
    assert refs["ref2"] is None


def test_pending_account_is_persisted_and_resume_skips_synced(api, client, keyed):
    a1 = api.default_account()
    a2 = api.account("Second")
    cid = _connect(client, a1).json()["id"]
    client.patch(f"/api/accounts/{a2}", json={"connectionId": cid})
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "awaiting_sms"
    import app.db as dbmod

    c = dbmod.connect()
    pending = c.execute("SELECT pending_account_id FROM bank_connections WHERE id=?", (cid,))
    assert pending.fetchone()[0] == a1
    c.close()
    body = client.post(f"/api/connections/{cid}/sms", json={"code": "0000"}).json()
    assert body["status"] == "connected"
    assert [r["accountId"] for r in body["accounts"]] == [a1, a2]
    c = dbmod.connect()
    assert (
        c.execute("SELECT pending_account_id FROM bank_connections WHERE id=?", (cid,)).fetchone()[
            0
        ]
        is None
    )
    batches = c.execute("SELECT COUNT(*) FROM import_batches WHERE connection_id=?", (cid,))
    assert batches.fetchone()[0] == 2
    c.close()
