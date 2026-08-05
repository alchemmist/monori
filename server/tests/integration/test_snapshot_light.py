import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from monori.server.app.deps import SnapshotResponse, TransactionResponse
from monori.server.app.routers.transactions import TransactionListResponse
from monori.server.tests.conftest import Api

pytestmark = pytest.mark.integration


def _ids(rows: list[TransactionResponse]) -> list[int]:
    return [transaction.id for transaction in rows]


def test_light_snapshot_returns_newest_window_in_canonical_order(
    api: Api,
    client: TestClient,
) -> None:
    ids = [api.tx(f"2026-01-{day:02d}T00:00:00", -day) for day in range(1, 8)]

    snap = TypeAdapter(SnapshotResponse).validate_python(
        client.get("/api/snapshot?light=1&limit=3").json(),
    )
    assert _ids(snap.transactions) == ids[-3:]
    assert snap.transactions_total == 7

    assert len(snap.accounts) == 1
    assert snap.budgets == []
    assert snap.connections == []


def test_light_snapshot_plus_paged_fill_reconstructs_the_full_ledger(
    api: Api,
    client: TestClient,
) -> None:
    ids = [api.tx(f"2026-02-{day:02d}T00:00:00", -day) for day in range(1, 8)]

    snap = TypeAdapter(SnapshotResponse).validate_python(
        client.get("/api/snapshot?light=1&limit=3").json(),
    )
    loaded = list(snap.transactions)
    offset = len(loaded)
    while offset < snap.transactions_total:
        page = TypeAdapter(TransactionListResponse).validate_python(
            client.get(f"/api/transactions?limit=2&offset={offset}").json(),
        )
        offset += len(page.rows)
        loaded = list(reversed(page.rows)) + loaded

    assert _ids(loaded) == ids
    assert _ids(loaded) == _ids(api.snapshot().transactions)


def test_snapshot_without_light_is_unpaged(api: Api, client: TestClient) -> None:
    ids = [api.tx(f"2026-03-{day:02d}T00:00:00", -day) for day in range(1, 6)]

    snap = TypeAdapter(SnapshotResponse).validate_python(client.get("/api/snapshot?limit=2").json())
    assert _ids(snap.transactions) == ids
    assert snap.transactions_total == 5


def test_light_snapshot_shorter_than_the_window_reports_its_own_total(
    api: Api,
    client: TestClient,
) -> None:
    api.tx("2026-04-01T00:00:00", -1)

    snap = TypeAdapter(SnapshotResponse).validate_python(
        client.get("/api/snapshot?light=1&limit=100").json(),
    )
    assert len(snap.transactions) == 1
    assert snap.transactions_total == 1


def test_light_snapshot_limit_is_bounded(client: TestClient) -> None:
    assert client.get("/api/snapshot?light=1&limit=0").status_code == 422
    assert client.get("/api/snapshot?light=1&limit=99999").status_code == 422
