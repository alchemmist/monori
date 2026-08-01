from typing import override

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from httpx2 import Response as HTTPXResponse
from pydantic import TypeAdapter

import app.connectors.fake  # noqa: F401  (registers the FakeConnector)
import app.db as dbmod
from app.connectors import base
from app.connectors.base import JsonObject, SmsRequiredError, SyncResult, SyncRow
from app.routers import connections
from app.routers.connections import ConnectionResponse
from tests.conftest import Api


@pytest.fixture(autouse=True)
def keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONORI_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _connect(client: TestClient, account_id: int | None) -> HTTPXResponse:
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


def test_create_auto_provisions_encryption_key(
    api: Api,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.delenv("MONORI_ENCRYPTION_KEY", raising=False)
    r = _connect(client, api.default_account())
    assert r.status_code == 200, r.text


def test_create_rejects_unknown_bank(client: TestClient) -> None:
    r = client.post(
        "/api/connections",
        json={
            "bank": "nope",
            "kind": "nope",
            "credentials": {"phone": "+7", "password": "p"},
        },
    )
    assert r.status_code == 400


def test_connection_appears_in_snapshot_without_secrets(
    api: Api,
    client: TestClient,
) -> None:
    r = _connect(client, api.default_account())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "disconnected"
    assert body["hasCredentials"] is True
    assert "credentials" not in body
    assert "credentials_encrypted" not in body
    conns = api.snapshot().connections
    assert len(conns) == 1
    assert conns[0].bank == "fake"


def test_two_phase_sync_then_incremental_dedup(api: Api, client: TestClient) -> None:
    acct = api.default_account()

    inc = api.group("Income", kind="income")
    exp = api.group("Spending", kind="expense")
    salary_cat = api.category("Salary", inc, keywords="salary")
    food_cat = api.category("Food", exp, keywords="lenta")
    cid = _connect(client, acct).json()["id"]

    r = client.post(f"/api/connections/{cid}/sync")
    assert r.json()["status"] == "awaiting_sms"
    assert api.snapshot().connections[0].status == "awaiting_sms"

    r = client.post(f"/api/connections/{cid}/sms", json={"code": "9999"})
    assert r.status_code == 502
    assert api.snapshot().connections[0].status == "error"

    assert client.post(f"/api/connections/{cid}/sms", json={"code": "0000"}).status_code == 409

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
    synced = [transaction for transaction in snap.transactions if transaction.source == "sync"]
    assert len(synced) == 2
    assert all(transaction.accountId == acct for transaction in synced)

    by_desc = {transaction.description: transaction for transaction in synced}
    assert by_desc["Lenta"].categoryId == food_cat
    assert by_desc["Salary"].categoryId == salary_cat
    assert snap.connections[0].status == "connected"
    assert snap.connections[0].lastSync is not None

    r = client.post(f"/api/connections/{cid}/sync")
    body = r.json()
    assert body["status"] == "connected"
    assert body["inserted"] == 0
    assert body["skipped"] == 2


def test_sms_without_pending_login_conflicts(api: Api, client: TestClient) -> None:
    cid = _connect(client, api.default_account()).json()["id"]
    r = client.post(f"/api/connections/{cid}/sms", json={"code": "0000"})
    assert r.status_code == 409


def test_cancel_clears_pending_login(api: Api, client: TestClient) -> None:
    cid = _connect(client, api.default_account()).json()["id"]
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "awaiting_sms"
    assert client.post(f"/api/connections/{cid}/cancel").status_code == 200
    assert api.snapshot().connections[0].status == "disconnected"

    assert client.post(f"/api/connections/{cid}/sms", json={"code": "0000"}).status_code == 409


def test_resync_replaces_pending_login(api: Api, client: TestClient) -> None:
    cid = _connect(client, api.default_account()).json()["id"]
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "awaiting_sms"

    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "awaiting_sms"
    assert client.post(f"/api/connections/{cid}/sms", json={"code": "0000"}).json()["status"] == (
        "connected"
    )


def test_delete_connection(api: Api, client: TestClient) -> None:
    cid = _connect(client, api.default_account()).json()["id"]
    assert client.delete(f"/api/connections/{cid}").status_code == 200
    assert api.snapshot().connections == []


class RetryOtpConnector(base.Connector):
    bank = "retryotp"
    kind = "retryotp"
    hidden = True

    def __init__(
        self,
        credentials: JsonObject,
        session: JsonObject | None = None,
        account_ref: str | None = None,
    ) -> None:
        self.credentials = credentials
        self.session = session
        self.account_ref = account_ref

    @override
    def sync(self, since: str | None = None) -> SyncResult:
        msg = "code sent"
        raise SmsRequiredError(msg)

    @override
    def resume_sync(self, code: str) -> SyncResult:
        if code != "4242":
            msg = "the bank rejected the code — check it and try again"
            raise SmsRequiredError(msg)
        return SyncResult([], session=None)

    @override
    def close(self) -> None:
        pass


def test_rejected_code_stays_awaiting(
    api: Api,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    assert body["message"] == connections.CODE_REJECTED
    assert api.snapshot().connections[0].status == "awaiting_sms"

    assert client.post(f"/api/connections/{cid}/sms", json={"code": "4242"}).json()["status"] == (
        "connected"
    )


class RefRequiredConnector(RetryOtpConnector):
    bank = "refreq"
    kind = "refreq"
    account_params = [base.ConnectorParam(name="account", required=True)]

    @override
    def sync(self, since: str | None = None) -> SyncResult:
        return SyncResult([], session=None)


def test_sync_requires_bank_ref_when_connector_demands_it(
    api: Api,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(base.REGISTRY, ("refreq", "refreq"), RefRequiredConnector)
    cid = client.post(
        "/api/connections",
        json={
            "bank": "refreq",
            "kind": "refreq",
            "credentials": {"phone": "+70000000000", "password": "pw"},
        },
    ).json()["id"]
    acct = api.default_account()
    assert client.patch(f"/api/accounts/{acct}", json={"connectionId": cid}).status_code == 200

    r = client.post(f"/api/connections/{cid}/sync")
    assert r.status_code == 400
    assert "bank account id" in r.json()["detail"]

    assert client.patch(f"/api/accounts/{acct}", json={"bankRef": "5858870594"}).status_code == 200
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "connected"


def test_available_lists_connectors_with_params(client: TestClient) -> None:
    r = client.get("/api/connections/available")
    assert r.status_code == 200
    banks = {c["bank"]: c for c in r.json()}
    assert "fake" not in banks
    tbank = banks["tbank"]
    assert tbank["label"] == "T-Bank (browser sync)"
    assert {p["name"] for p in tbank["connectionParams"]} == {"phone", "password"}
    assert [p["name"] for p in tbank["accountParams"]] == ["account"]


def test_one_connection_syncs_multiple_accounts(api: Api, client: TestClient) -> None:
    a1 = api.default_account()
    a2 = api.account("Savings")
    cid = _connect(client, a1).json()["id"]
    r = client.patch(f"/api/accounts/{a2}", json={"connectionId": cid, "bankRef": " 8121254731 "})
    assert r.status_code == 200
    snap = api.snapshot()
    linked = {account.id: account for account in snap.accounts}
    assert linked[a1].connectionId == cid
    assert linked[a2].connectionId == cid
    assert linked[a2].bankRef == "8121254731"

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
    txs = api.snapshot().transactions
    assert len([transaction for transaction in txs if transaction.accountId == a1]) == 2
    assert len([transaction for transaction in txs if transaction.accountId == a2]) == 2


def test_sync_requires_a_linked_account(client: TestClient) -> None:
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


def test_delete_connection_unlinks_accounts(api: Api, client: TestClient) -> None:
    a1 = api.default_account()
    cid = _connect(client, a1).json()["id"]
    assert api.snapshot().accounts[0].connectionId == cid
    client.delete(f"/api/connections/{cid}")
    snap = api.snapshot()
    assert snap.connections == []
    assert snap.accounts[0].connectionId is None


def test_unlink_account_via_patch(api: Api, client: TestClient) -> None:
    a1 = api.default_account()
    _connect(client, a1)
    r = client.patch(f"/api/accounts/{a1}", json={"connectionId": 0})
    assert r.status_code == 200
    assert api.snapshot().accounts[0].connectionId is None
    assert len(api.snapshot().connections) == 1


def test_link_rejects_unknown_connection(api: Api, client: TestClient) -> None:
    r = client.patch(f"/api/accounts/{api.default_account()}", json={"connectionId": 999})
    assert r.status_code == 400


def test_missing_required_credentials_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/connections",
        json={"bank": "tbank", "kind": "playwright", "credentials": {"phone": "+7"}},
    )
    assert r.status_code == 400
    assert "password" in r.json()["detail"]


class SinceRecorder(base.Connector):
    bank = "sincer"
    kind = "sincer"
    hidden = True
    calls: list[tuple[str | None, str | None]] = []

    def __init__(
        self,
        credentials: JsonObject,
        session: JsonObject | None = None,
        account_ref: str | None = None,
    ) -> None:
        self.credentials = credentials
        self.session = session
        self.account_ref = account_ref

    @override
    def sync(self, since: str | None = None) -> SyncResult:
        SinceRecorder.calls.append((self.account_ref, since))
        return SyncResult([], session={"token": "ok"})

    @override
    def close(self) -> None:
        pass


def test_newly_linked_account_gets_a_full_pull(
    api: Api,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_pending_account_is_persisted_and_resume_skips_synced(
    api: Api,
    client: TestClient,
) -> None:
    a1 = api.default_account()
    a2 = api.account("Second")
    cid = _connect(client, a1).json()["id"]
    client.patch(f"/api/accounts/{a2}", json={"connectionId": cid})
    assert client.post(f"/api/connections/{cid}/sync").json()["status"] == "awaiting_sms"

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


class MultiCardConnector(base.Connector):
    bank = "multicard"
    kind = "multicard"
    hidden = True
    rows = [
        SyncRow("2026-03-01T09:00:00", -100, "A", "", "", "*8181"),
        SyncRow("2026-03-01T10:00:00", -200, "B", "", "", "*2947"),
        SyncRow("2026-03-01T11:00:00", -300, "C", "", "", "*1111"),
    ]

    @override
    def sync(self, since: str | None = None) -> SyncResult:
        return SyncResult(list(self.rows), session={"token": "ok"})


def _connect_multicard(client: TestClient, account_id: int) -> int:
    r = client.post(
        "/api/connections",
        json={"bank": "multicard", "kind": "multicard", "credentials": {"phone": "+7"}},
    )
    link = client.patch(f"/api/accounts/{account_id}", json={"connectionId": r.json()["id"]})
    assert link.status_code == 200, link.text
    response = TypeAdapter(ConnectionResponse).validate_python(r.json())
    return response.id


def test_sync_routes_rows_by_bound_card_tail(
    api: Api,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(base.REGISTRY, ("multicard", "multicard"), MultiCardConnector)
    main = api.default_account()
    other = api.account("Other card", cardTails=["2947"])
    cid = _connect_multicard(client, main)

    body = client.post(f"/api/connections/{cid}/sync").json()
    assert body["status"] == "connected"
    assert body["inserted"] == 3

    by_account = {r["accountId"]: r for r in body["accounts"]}
    assert by_account[main]["inserted"] == 2
    assert by_account[other]["inserted"] == 1

    assert body["unmappedTails"] == [
        {"tail": "1111", "rows": 1},
        {"tail": "8181", "rows": 1},
    ]

    snap = api.snapshot()
    routed = {transaction.description: transaction.accountId for transaction in snap.transactions}
    assert routed["B"] == other
    assert routed["A"] == main
    assert routed["C"] == main


def test_single_card_feed_reports_no_unmapped_tails(
    api: Api,
    client: TestClient,
) -> None:
    cid = _connect(client, api.default_account()).json()["id"]
    client.post(f"/api/connections/{cid}/sync")
    body = client.post(f"/api/connections/{cid}/sms", json={"code": "0000"}).json()
    assert body["status"] == "connected"
    assert body["unmappedTails"] == []


def test_sync_routing_matches_longer_stored_tails_by_suffix(
    api: Api,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(base.REGISTRY, ("multicard", "multicard"), MultiCardConnector)
    main = api.default_account()

    other = api.account("Other card", cardTails=["55362947"])
    cid = _connect_multicard(client, main)

    body = client.post(f"/api/connections/{cid}/sync").json()
    by_account = {r["accountId"]: r for r in body["accounts"]}
    assert by_account[other]["inserted"] == 1
    routed = {
        transaction.description: transaction.accountId
        for transaction in api.snapshot().transactions
    }
    assert routed["B"] == other


def test_sync_routing_treats_duplicated_tail_as_unmapped(
    api: Api,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(base.REGISTRY, ("multicard", "multicard"), MultiCardConnector)
    main = api.default_account()
    api.account("One", cardTails=["2947"])
    api.account("Two", cardTails=["2947"])
    cid = _connect_multicard(client, main)

    body = client.post(f"/api/connections/{cid}/sync").json()

    by_account = {r["accountId"]: r for r in body["accounts"]}
    assert by_account[main]["inserted"] == 3
    assert {u["tail"] for u in body["unmappedTails"]} == {"1111", "2947", "8181"}
    routed = {
        transaction.description: transaction.accountId
        for transaction in api.snapshot().transactions
    }
    assert routed["B"] == main


def test_overlapping_feeds_do_not_duplicate_rows_across_accounts(
    api: Api,
    client: TestClient,
) -> None:
    """
    Two accounts on one connection whose pulls return the same feed (the fake.

    without a bank_ref does exactly that) must not land the same operations.
    twice — once per account. The second delivery is recognized by day, amount
    and description, since the copies differ in account and so escape the
    per-account hash.
    """
    a1 = api.default_account()
    a2 = api.account("Twin")
    cid = _connect(client, a1).json()["id"]
    r = client.patch(f"/api/accounts/{a2}", json={"connectionId": cid})
    assert r.status_code == 200

    client.post(f"/api/connections/{cid}/sync")
    body = client.post(f"/api/connections/{cid}/sms", json={"code": "0000"}).json()
    assert body["status"] == "connected"
    assert body["inserted"] == 2
    assert body["skipped"] == 2

    txs = api.snapshot().transactions
    assert len(txs) == 2
    assert {transaction.accountId for transaction in txs} == {a1}
