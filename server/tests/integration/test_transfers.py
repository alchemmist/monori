import re

import pytest
from fastapi.testclient import TestClient

from app.deps import TransactionResponse
from tests.conftest import Api, TransactionOptions, login_as

pytestmark = pytest.mark.integration


def legs(api: Api, transfer_id: str) -> list[TransactionResponse]:
    return [
        transaction
        for transaction in api.snapshot().transactions
        if transaction.transfer_id == transfer_id
    ]


def pair(
    api: Api,
    out_account: int,
    in_account: int,
    amount: int = 5000,
    dates: tuple[str, str] = ("2026-03-10", "2026-03-10"),
) -> tuple[int, int]:
    """
    Two ordinary transactions that together look like a transfer, as a bank.

    would deliver them: nothing links them yet.
    """
    out_date, in_date = dates
    out_id = api.tx(f"{out_date}T09:00:00", -amount, TransactionOptions(account_id=out_account))
    in_id = api.tx(f"{in_date}T18:00:00", amount, TransactionOptions(account_id=in_account))
    return out_id, in_id


def test_transfer_creates_linked_pair(api: Api) -> None:
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000, comment="move")

    rows = legs(api, transfer_id)
    assert len(rows) == 2
    assert {transaction.account_id: transaction.amount for transaction in rows} == {
        a: -5000,
        b: 5000,
    }
    assert all(
        transaction.category_id is None and transaction.source == "transfer" for transaction in rows
    )
    assert sum(transaction.amount for transaction in rows) == 0


def test_transfer_shows_up_as_an_entity_in_the_snapshot(api: Api) -> None:
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000, comment="move")

    entity = next(transfer for transfer in api.snapshot().transfers if transfer.id == transfer_id)
    out_leg, in_leg = (api.tx_by(entity.out_tx_id), api.tx_by(entity.in_tx_id))
    assert out_leg.amount == -5000
    assert out_leg.account_id == a
    assert in_leg.amount == 5000
    assert in_leg.account_id == b
    assert entity.origin == "manual"
    assert entity.note == "move"


def test_transfer_rejects_same_account(api: Api, client: TestClient) -> None:
    a = api.default_account()
    r = client.post(
        "/api/transfers",
        json={"fromAccountId": a, "toAccountId": a, "amount": 100, "date": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 400


def test_transfer_rejects_unknown_account(api: Api, client: TestClient) -> None:
    a = api.default_account()
    r = client.post(
        "/api/transfers",
        json={"fromAccountId": a, "toAccountId": 999, "amount": 100, "date": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 400


def test_transfer_rejects_non_positive_amount(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    r = client.post(
        "/api/transfers",
        json={"fromAccountId": a, "toAccountId": b, "amount": 0, "date": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 422


def test_link_merges_an_existing_pair_without_touching_the_rows(
    api: Api,
    client: TestClient,
) -> None:
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b)
    before = (api.tx_by(out_id).amount, api.tx_by(in_id).amount)

    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    assert r.status_code == 200, r.text
    transfer_id = r.json()["transfer_id"]

    assert {transaction.id for transaction in legs(api, transfer_id)} == {out_id, in_id}

    assert (api.tx_by(out_id).amount, api.tx_by(in_id).amount) == before
    assert (
        next(transfer for transfer in api.snapshot().transfers if transfer.id == transfer_id).origin
        == "manual"
    )


def test_link_moves_categories_aside_and_split_gives_them_back(
    api: Api,
    client: TestClient,
) -> None:
    g = api.group("Living")
    cat = api.category("Groceries", g)
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b)
    client.patch(f"/api/transactions/{out_id}", json={"categoryId": cat})

    transfer_id = client.post(
        "/api/transfers/link",
        json={"outTxId": out_id, "inTxId": in_id},
    ).json()["transfer_id"]
    assert api.tx_by(out_id).category_id is None

    assert client.delete(f"/api/transfers/{transfer_id}").status_code == 200
    assert api.tx_by(out_id).category_id == cat


def test_split_keeps_both_transactions(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000)
    out_id, in_id = (
        transaction.id for transaction in sorted(legs(api, transfer_id), key=lambda row: row.amount)
    )

    assert client.delete(f"/api/transfers/{transfer_id}").status_code == 200
    assert legs(api, transfer_id) == []
    assert not api.snapshot().transfers

    assert api.tx_by(out_id).transfer_id is None
    assert api.tx_by(in_id).transfer_id is None

    assert client.delete(f"/api/transfers/{transfer_id}").status_code == 404


def test_split_frees_the_legs_to_be_linked_again(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b)
    first = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id}).json()
    client.delete(f"/api/transfers/{first['transfer_id']}")
    second = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    assert second.status_code == 200


@pytest.mark.parametrize(
    ("amounts", "same_account"),
    [
        ((-5000, -5000), False),
        ((5000, 5000), False),
        ((-5000, 5000), True),
    ],
)
def test_link_rejects_pairs_that_are_not_a_transfer(
    api: Api,
    client: TestClient,
    amounts: tuple[int, int],
    *,
    same_account: bool,
) -> None:
    a = api.default_account()
    b = a if same_account else api.account("Vault")
    out_id = api.tx("2026-03-10T09:00:00", amounts[0], TransactionOptions(account_id=a))
    in_id = api.tx("2026-03-10T18:00:00", amounts[1], TransactionOptions(account_id=b))
    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    assert r.status_code == 400


def test_link_rejects_a_leg_already_in_a_transfer(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    third = api.account("Pocket")
    out_id, in_id = pair(api, a, b)
    client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    other = api.tx("2026-03-10T18:00:00", 5000, TransactionOptions(account_id=third))
    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": other})
    assert r.status_code == 400


def test_link_rejects_another_users_transaction(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b)
    client.headers.update(login_as(client, "other@example.com"))
    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    assert r.status_code == 400


def test_detect_merges_a_same_day_pair(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b)

    result = client.post("/api/transfers/detect").json()
    assert result["merged"]
    assert result["merged"][0]["out_tx_id"] == out_id
    assert api.tx_by(in_id).transfer_id == result["merged"][0]["id"]
    assert next(iter(api.snapshot().transfers)).origin == "matched"


def test_detect_leaves_a_distant_pair_as_a_suggestion(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b, dates=("2026-03-10", "2026-03-13"))

    result = client.post("/api/transfers/detect").json()
    assert result["merged"] == []
    assert result["suggested"] == 1

    rows = client.get("/api/transfers/suggestions").json()
    assert [(p["out_tx_id"], p["in_tx_id"]) for p in rows["rows"]] == [(out_id, in_id)]
    assert {t["id"] for t in rows["transactions"]} == {out_id, in_id}


def test_dismissed_suggestions_stop_coming_back(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    out_id, in_id = pair(api, a, b, dates=("2026-03-10", "2026-03-13"))

    client.post("/api/transfers/suggestions/dismiss", json={"outTxId": out_id, "inTxId": in_id})
    assert client.get("/api/transfers/suggestions").json()["rows"] == []
    assert client.post("/api/transfers/detect").json()["suggested"] == 0


def test_detect_leaves_a_disagreeing_same_day_pair_as_a_suggestion(
    api: Api,
    client: TestClient,
) -> None:
    """
    An inflow labeled as a transfer whose true counterpart cannot pair (say,.

    both legs landed on one account) must not swallow a purchase that merely.
    matches the amount — the pair is offered, not merged.
    """
    a = api.default_account()
    b = api.account("Vault")
    out_id = api.tx(
        "2026-03-10T09:00:00",
        -100000,
        TransactionOptions(account_id=a, description="IP Elyan A.Kh"),
    )
    in_id = api.tx(
        "2026-03-10T18:00:00",
        100000,
        TransactionOptions(
            account_id=b,
            description="Transfer between own accounts",
        ),
    )

    result = client.post("/api/transfers/detect").json()
    assert result["merged"] == []
    assert result["suggested"] == 1

    rows = client.get("/api/transfers/suggestions").json()
    assert [(p["out_tx_id"], p["in_tx_id"]) for p in rows["rows"]] == [(out_id, in_id)]
    assert rows["rows"][0]["mismatch"] is True


def test_detect_is_idempotent(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    pair(api, a, b)

    first = client.post("/api/transfers/detect").json()
    second = client.post("/api/transfers/detect").json()
    assert len(first["merged"]) == 1
    assert second["merged"] == []
    assert len(api.snapshot().transfers) == 1


def test_transfers_list_is_scoped_to_the_user(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    api.transfer(a, b, 5000)
    assert len(client.get("/api/transfers").json()["rows"]) == 1

    client.headers.update(login_as(client, "stranger@example.com"))
    assert client.get("/api/transfers").json()["rows"] == []


def test_deleting_one_leg_leaves_no_dangling_transfer_pointer(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000)
    out_id, in_id = (
        transaction.id for transaction in sorted(legs(api, transfer_id), key=lambda row: row.amount)
    )

    assert client.delete(f"/api/transactions/{out_id}").status_code == 200

    snap = api.snapshot()
    assert snap.transfers == []
    survivor = next(transaction for transaction in snap.transactions if transaction.id == in_id)
    assert survivor.transfer_id is None


def test_bulk_delete_of_one_leg_also_frees_the_other(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    transfer_id = api.transfer(a, b, 5000)
    out_id, in_id = (
        transaction.id for transaction in sorted(legs(api, transfer_id), key=lambda row: row.amount)
    )

    r = client.post("/api/transactions/bulk", json={"action": "delete", "ids": [out_id]})
    assert r.status_code == 200

    snap = api.snapshot()
    assert snap.transfers == []
    assert (
        next(
            transaction for transaction in snap.transactions if transaction.id == in_id
        ).transfer_id
        is None
    )


def test_deleting_a_leg_restores_the_partner_category(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    group = api.group("Daily")
    cat = api.category("Groceries", group)
    out_id, in_id = pair(api, a, b)
    r = client.patch(f"/api/transactions/{out_id}", json={"categoryId": cat})
    assert r.status_code == 200, r.text
    assert (
        client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id}).status_code
        == 200
    )

    client.delete(f"/api/transactions/{in_id}")

    survivor = next(
        transaction for transaction in api.snapshot().transactions if transaction.id == out_id
    )
    assert survivor.category_id == cat


def test_link_reports_an_unknown_transaction_by_message(api: Api, client: TestClient) -> None:
    a = api.default_account()
    out_id = api.tx("2026-03-10T09:00:00", -5000, TransactionOptions(account_id=a))
    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": 999999})
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown transaction"


def test_link_reports_two_outflows_by_message(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    out_id = api.tx("2026-03-10T09:00:00", -5000, TransactionOptions(account_id=a))
    in_id = api.tx("2026-03-10T18:00:00", -5000, TransactionOptions(account_id=b))
    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    assert r.status_code == 400
    assert r.json()["detail"] == "a transfer needs one outflow and one inflow"


def test_link_reports_same_account_by_message(api: Api, client: TestClient) -> None:
    a = api.default_account()
    out_id = api.tx("2026-03-10T09:00:00", -5000, TransactionOptions(account_id=a))
    in_id = api.tx("2026-03-10T18:00:00", 5000, TransactionOptions(account_id=a))
    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    assert r.status_code == 400
    assert r.json()["detail"] == "both legs are on the same account"


def test_link_reports_an_already_linked_leg_by_message(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    third = api.account("Pocket")
    out_id, in_id = pair(api, a, b)
    client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": in_id})
    other = api.tx("2026-03-10T18:00:00", 5000, TransactionOptions(account_id=third))
    r = client.post("/api/transfers/link", json={"outTxId": out_id, "inTxId": other})
    assert r.status_code == 400
    assert r.json()["detail"] == "already part of a transfer"


def test_dismiss_reports_an_unknown_transaction_by_message(api: Api, client: TestClient) -> None:
    a = api.default_account()
    out_id = api.tx("2026-03-10T09:00:00", -5000, TransactionOptions(account_id=a))
    r = client.post(
        "/api/transfers/suggestions/dismiss",
        json={"outTxId": out_id, "inTxId": 999999},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown transaction"


def test_transfer_created_at_is_a_full_iso_timestamp(api: Api, client: TestClient) -> None:
    a = api.default_account()
    b = api.account("Vault")
    api.transfer(a, b, 5000)
    row = client.get("/api/transfers").json()["rows"][0]
    assert "created_at" in row
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", row["created_at"])


def test_detection_never_pairs_a_reconcile_adjustment(api: Api, client: TestClient) -> None:
    """
    A reconcile adjustment is bookkeeping: it exists to bend a balance to the.

    bank's figure, not because money moved anywhere. Matching it against a.
    real transaction would merge fiction with fact.
    """
    a = api.default_account()
    b = api.account("Vault")
    api.tx("2026-03-10T09:00:00", -5000, TransactionOptions(account_id=a))
    r = client.post(f"/api/accounts/{b}/reconcile", json={"actualBalance": 5000})
    assert r.status_code == 200
    assert r.json()["delta"] == 5000

    result = client.post("/api/transfers/detect").json()
    assert result["merged"] == []
    assert result["suggested"] == 0
    assert client.get("/api/transfers/suggestions").json()["rows"] == []
