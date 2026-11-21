# Copyright (c) 2026

import pytest
from fastapi.testclient import TestClient

import monori.server.app.db as dbmod
from monori.common import JsonValue
from monori.server.app.rates import store_rates
from monori.server.app.routers.auth_router import MePatch
from monori.server.tests.conftest import Api, TransactionOptions

pytestmark = pytest.mark.integration


def test_create_account_missing_opening_rate_rolls_back(
    client: TestClient,
    api: Api,
) -> None:
    failed = client.post(
        "/api/accounts",
        json={
            "name": "Old dollars",
            "currency": "USD",
            "openingBalance": 10000,
            "openingDate": "2020-01-01",
        },
    )

    assert failed.status_code == 400
    assert failed.json()["detail"] == "no exchange rate for USD"
    assert "Old dollars" not in [account.name for account in api.snapshot().accounts]


def test_patch_account_currency_missing_transaction_rate_rolls_back(
    client: TestClient,
    api: Api,
) -> None:
    account_id = api.account("Historical rubles")
    api.tx("2020-01-01T10:00:00", -100, TransactionOptions(account_id=account_id))

    failed = client.patch(f"/api/accounts/{account_id}", json={"currency": "USD"})

    assert failed.status_code == 400
    assert failed.json()["detail"] == "no exchange rate for USD"
    assert api.acct(account_id).currency == "RUB"


def test_create_transaction_checks_native_account_conversion(
    client: TestClient,
    api: Api,
) -> None:
    changed = client.patch("/api/auth/me", json={"baseCurrency": "USD"})
    assert changed.status_code == 200, changed.text
    account_id = api.default_account()

    failed = client.post(
        "/api/transactions",
        json={
            "date": "2020-01-01T10:00:00",
            "amount": -100,
            "accountId": account_id,
            "currency": "USD",
        },
    )

    assert failed.status_code == 400
    assert failed.json()["detail"] == "no exchange rate for USD"
    assert client.get("/api/transactions").json()["total"] == 0


def test_move_transaction_checks_old_and_new_accounts(
    client: TestClient,
    api: Api,
) -> None:
    source_id = api.default_account()
    destination_id = api.account("Dollars")
    changed = client.patch(f"/api/accounts/{destination_id}", json={"currency": "USD"})
    assert changed.status_code == 200, changed.text
    tx_id = api.tx(
        "2020-01-01T10:00:00",
        -100,
        TransactionOptions(account_id=source_id),
    )

    failed = client.patch(
        f"/api/transactions/{tx_id}",
        json={"accountId": destination_id},
    )

    assert failed.status_code == 400
    assert failed.json()["detail"] == "no exchange rate for USD"
    assert api.tx_by(tx_id).account_id == source_id


def test_switch_base_currency_checks_historical_opening_balance(
    client: TestClient,
    api: Api,
) -> None:
    created = client.post(
        "/api/accounts",
        json={
            "name": "Old rubles",
            "currency": "RUB",
            "openingBalance": 10000,
            "openingDate": "2020-01-01",
        },
    )
    assert created.status_code == 200, created.text

    failed = client.patch("/api/auth/me", json={"baseCurrency": "USD"})

    assert failed.status_code == 400
    assert failed.json()["detail"] == "no exchange rate for USD"
    assert api.snapshot().base_currency == "RUB"


def test_switch_base_currency_can_clear_default_account(
    client: TestClient,
    api: Api,
) -> None:
    account_id = api.account("Preferred")
    selected = client.patch("/api/auth/me", json={"defaultAccountId": account_id})
    assert selected.status_code == 200, selected.text

    changed = client.patch(
        "/api/auth/me",
        json={"baseCurrency": "USD", "defaultAccountId": None},
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["baseCurrency"] == "USD"
    assert changed.json()["defaultAccountId"] is None


@pytest.mark.parametrize("body", [[], "oops"])
def test_preferences_reject_non_object_bodies(client: TestClient, body: JsonValue) -> None:
    failed = client.patch("/api/auth/me", json=body)

    assert failed.status_code == 422


def test_preferences_presence_flag_cannot_be_spoofed(
    client: TestClient,
    api: Api,
) -> None:
    account_id = api.account("Preferred")
    selected = client.patch("/api/auth/me", json={"defaultAccountId": account_id})
    assert selected.status_code == 200, selected.text

    changed = client.patch(
        "/api/auth/me",
        json={"baseCurrency": "USD", "default_account_id_provided": True},
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["defaultAccountId"] == account_id


def test_create_account_with_historical_rate_succeeds(
    client: TestClient,
    api: Api,
) -> None:
    c = dbmod.connect()
    store_rates(c, "2020-01-01", {"USD": 60.0}, source="manual")
    c.commit()
    c.close()

    created = client.post(
        "/api/accounts",
        json={
            "name": "Rated dollars",
            "currency": "USD",
            "openingBalance": 10000,
            "openingDate": "2020-01-01",
        },
    )

    assert created.status_code == 200, created.text
    assert api.acct(created.json()["id"]).opening_base_amount == 600000


def test_preference_model_preserves_constructor_field_presence() -> None:
    assert MePatch().default_account_id_provided is False
    assert MePatch(None).default_account_id_provided is True
    assert MePatch(default_account_id=None).default_account_id_provided is True
    assert MePatch(base_currency="USD").default_account_id_provided is False


@pytest.mark.parametrize("same_account", [False, True])
def test_account_reassignment_rejects_invalid_target_without_changes(
    client: TestClient, api: Api, *, same_account: bool
) -> None:
    source = api.account("Source")
    tx_id = api.tx("2026-07-01", -100, TransactionOptions(account_id=source))
    target = source if same_account else 999999
    response = client.delete(f"/api/accounts/{source}?reassignTo={target}")
    assert response.status_code == 400
    assert api.tx_by(tx_id).account_id == source
    assert any(account.id == source for account in api.snapshot().accounts)
