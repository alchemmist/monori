import sqlite3
from typing import Never

import httpx
import pytest
from fastapi.testclient import TestClient

from monori.server.app.rates import store_rates
from monori.server.app.routers import auth_router
from monori.server.app.routers import rates as rates_router
from monori.server.tests.conftest import AccountOptions, Api, TransactionOptions, login_as

pytestmark = pytest.mark.integration

RATE_DAY = "2026-07-01"
TESTER = "tester@example.com"


@pytest.fixture
def admin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    Return the same signed-in user with administrator access.

    Rates are one shared table, so setting one is an admin's job; the flag is
    re-synced from ``MONORI_ADMIN_EMAILS`` on every login.
    """
    monkeypatch.setenv("MONORI_ADMIN_EMAILS", TESTER)
    client.headers.update(login_as(client, TESTER))
    return client


def _set_rate(
    admin: TestClient, code: str, rub_per_unit: float, day: str = RATE_DAY
) -> dict[str, str | int]:
    r = admin.put(f"/api/rates/{code}", json={"day": day, "rubPerUnit": rub_per_unit})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_transaction_inherits_its_account_currency(api: Api) -> None:
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    tx = api.tx("2026-07-05T10:00:00", -10000, TransactionOptions(account_id=lari))
    assert api.tx_by(tx).currency == "GEL"


def test_a_transaction_may_name_a_currency_of_its_own(api: Api) -> None:
    """
    Ensure a transaction can override its account currency.

    The row records what was spent rather than inheriting a label permanently.
    """
    rubles = api.default_account()
    tx = api.tx(
        "2026-07-05T10:00:00",
        -10000,
        TransactionOptions(account_id=rubles, currency="usd"),
    )
    assert api.tx_by(tx).currency == "USD"


def test_an_unknown_currency_is_rejected(client: TestClient, api: Api) -> None:
    r = client.post(
        "/api/transactions",
        json={
            "date": "2026-07-05T10:00:00",
            "amount": -100,
            "accountId": api.default_account(),
            "currency": "XYZ",
        },
    )
    assert r.status_code == 400
    assert "XYZ" in r.json()["detail"]


def test_base_amount_is_the_row_converted_into_the_reporting_currency(
    admin: TestClient, api: Api
) -> None:
    _set_rate(admin, "GEL", 30.0)
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    tx = api.tx("2026-07-05T10:00:00", -10000, TransactionOptions(account_id=lari))
    row = api.tx_by(tx)
    assert row.amount == -10000
    assert row.base_amount == -300000


def test_base_amount_of_the_reporting_currency_is_the_amount_itself(api: Api) -> None:
    tx = api.tx("2026-07-05T10:00:00", -12345)
    row = api.tx_by(tx)
    assert row.base_amount == row.amount == -12345


def test_switching_the_reporting_currency_reprices_the_ledger(admin: TestClient, api: Api) -> None:
    _set_rate(admin, "GEL", 30.0)
    _set_rate(admin, "USD", 90.0)
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    tx = api.tx("2026-07-05T10:00:00", -30000, TransactionOptions(account_id=lari))
    assert api.tx_by(tx).base_amount == -900000

    r = admin.patch("/api/auth/me", json={"baseCurrency": "USD"})
    assert r.status_code == 200, r.text
    assert r.json()["baseCurrency"] == "USD"
    assert api.tx_by(tx).base_amount == -10000
    assert api.tx_by(tx).amount == -30000
    assert api.snapshot().base_currency == "USD"


def test_switching_to_an_unknown_reporting_currency_is_rejected(client: TestClient) -> None:
    assert client.patch("/api/auth/me", json={"baseCurrency": "XYZ"}).status_code == 400


def test_switching_reporting_currency_converts_budgets_and_goals(
    admin: TestClient, api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_router, "today_iso", lambda: RATE_DAY)
    _set_rate(admin, "USD", 90.0)
    goal = admin.post(
        "/api/categories",
        json={
            "name": "House",
            "groupId": api.group("Plans", kind="goal"),
            "goalTarget": 9000,
            "goalTargetDate": "2027-01-01",
        },
    )
    assert goal.status_code == 200, goal.text
    category_id = goal.json()["id"]
    budget = admin.put(
        "/api/budgets",
        json={"categoryId": category_id, "year": 2026, "month": 7, "amount": 9000},
    )
    assert budget.status_code == 200, budget.text

    changed = admin.patch("/api/auth/me", json={"baseCurrency": "USD"})

    assert changed.status_code == 200, changed.text
    snapshot = admin.get("/api/snapshot").json()
    assert snapshot["baseCurrency"] == "USD"
    assert snapshot["budgets"][0]["amount"] == 100
    category = next(row for row in snapshot["categories"] if row["id"] == category_id)
    assert category["goalTarget"] == 100


def test_reporting_currency_failure_rolls_back_plans(
    admin: TestClient, api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_router, "today_iso", lambda: "2020-01-01")
    goal = admin.post(
        "/api/categories",
        json={
            "name": "House",
            "groupId": api.group("Plans", kind="goal"),
            "goalTarget": 9000,
            "goalTargetDate": "2027-01-01",
        },
    )
    assert goal.status_code == 200, goal.text
    category_id = goal.json()["id"]
    budget = admin.put(
        "/api/budgets",
        json={"categoryId": category_id, "year": 2026, "month": 7, "amount": 9000},
    )
    assert budget.status_code == 200, budget.text

    failed = admin.patch("/api/auth/me", json={"baseCurrency": "USD"})

    assert failed.status_code == 400, failed.text
    snapshot = admin.get("/api/snapshot").json()
    assert snapshot["baseCurrency"] == "RUB"
    assert snapshot["budgets"][0]["amount"] == 9000
    category = next(row for row in snapshot["categories"] if row["id"] == category_id)
    assert category["goalTarget"] == 9000


def test_correcting_a_rate_reprices_what_it_priced(admin: TestClient, api: Api) -> None:
    _set_rate(admin, "GEL", 30.0)
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    tx = api.tx("2026-07-05T10:00:00", -10000, TransactionOptions(account_id=lari))
    assert api.tx_by(tx).base_amount == -300000
    assert _set_rate(admin, "GEL", 40.0)["repriced"] == 1
    assert api.tx_by(tx).base_amount == -400000


def test_refresh_pulls_the_feed_and_reprices(
    admin: TestClient, api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    tx = api.tx("2026-07-05T10:00:00", -10000, TransactionOptions(account_id=lari))

    def fake_refresh(
        c: sqlite3.Connection,
        day: str | None = None,
        client: httpx.Client | None = None,
    ) -> int:
        del client
        return store_rates(c, day or RATE_DAY, {"GEL": 25.0})

    def fake_backfill(_c: sqlite3.Connection, days: int) -> int:
        return days

    monkeypatch.setattr(rates_router, "refresh", fake_refresh)
    monkeypatch.setattr(rates_router, "backfill", fake_backfill)

    body = admin.post("/api/rates/refresh?days=3").json()
    assert body["stored"] == 1
    assert body["days"] == 4
    assert body["repriced"] == 1
    assert api.tx_by(tx).base_amount == -250000


def test_refresh_reports_an_unreachable_feed_as_a_bad_gateway(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(
        _c: sqlite3.Connection,
        day: str | None = None,
        client: httpx.Client | None = None,
    ) -> Never:
        del day, client
        msg = "offline"
        raise httpx.ConnectError(msg)

    monkeypatch.setattr(rates_router, "refresh", explode)
    r = admin.post("/api/rates/refresh")
    assert r.status_code == 502
    assert "rate feed" in r.json()["detail"]


def test_a_rate_may_not_be_set_for_the_pivot_itself(admin: TestClient) -> None:
    r = admin.put("/api/rates/RUB", json={"rubPerUnit": 2.0})
    assert r.status_code == 400


def test_a_malformed_day_is_rejected_rather_than_sorted_wrongly(admin: TestClient) -> None:
    """
    Reject a malformed exchange-rate day.

    Rates are looked up by comparing the day as text, which only orders
    correctly for ISO dates — a malformed one would silently return a rate from
    the wrong day.
    """
    assert (
        admin.put("/api/rates/USD", json={"day": "01/07/2026", "rubPerUnit": 80}).status_code == 400
    )
    assert admin.get("/api/rates?day=yesterday").status_code == 400


def test_setting_a_rate_is_not_an_ordinary_user_business(client: TestClient) -> None:
    """
    Restrict shared exchange-rate changes to administrators.

    One shared table with no owner column: a hand-set rate moves every user's
    totals, so it is an admin's call. The per-user case — my bank converted at
    its own rate — is recorded on the transfer instead.
    """
    assert client.put("/api/rates/USD", json={"rubPerUnit": 80}).status_code == 403
    assert client.post("/api/rates/refresh").status_code == 403
    assert client.get("/api/rates").status_code == 200


def test_rates_endpoint_serves_the_registry_and_the_quotes(client: TestClient) -> None:
    body = client.get("/api/rates").json()
    assert body["baseCurrency"] == "RUB"
    codes = {c["code"] for c in body["currencies"]}
    assert {"RUB", "USD", "GEL"} <= codes
    assert {r["code"] for r in body["rates"]} == codes
    assert all(c["minorUnits"] == 2 for c in body["currencies"])


def test_two_currencies_with_the_same_amount_are_not_each_other_duplicate(
    client: TestClient, api: Api
) -> None:
    """
    Keep currency in the dedup fingerprint.

    One hundred lari and one hundred rubles on the
    same day with the same description are different money, and an import that
    collapsed one into the other would lose it silently.
    """
    account = api.default_account()
    api.tx(
        "2026-07-05T10:00:00", -10000, TransactionOptions(account_id=account, description="Coffee")
    )
    api.tx(
        "2026-07-05T10:00:00",
        -10000,
        TransactionOptions(account_id=account, description="Coffee", currency="GEL"),
    )
    rows = client.post(
        "/api/import/commit",
        json={
            "accountId": account,
            "rows": [
                {
                    "date": "2026-07-05T10:00:00",
                    "amount": -10000,
                    "description": "Coffee",
                    "currency": "RUB",
                }
            ],
        },
    ).json()
    assert rows == {
        "inserted": 0,
        "skipped": 1,
        "transfersMerged": 0,
        "transfersSuggested": 0,
    }


def test_a_transfer_between_two_currencies_carries_each_leg_in_its_own(
    admin: TestClient, api: Api
) -> None:
    _set_rate(admin, "GEL", 30.0)
    rubles = api.default_account()
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    api.transfer(rubles, lari, 300000, date="2026-07-05T12:00:00")
    legs = {t.account_id: t for t in api.snapshot().transactions}
    assert legs[rubles].amount == -300000
    assert legs[rubles].currency == "RUB"
    assert legs[lari].amount == 10000
    assert legs[lari].currency == "GEL"
    assert legs[lari].base_amount == -legs[rubles].base_amount


def test_a_stated_landing_amount_beats_the_published_rate(admin: TestClient, api: Api) -> None:
    """
    Prefer the transfer's stated landing amount.

    A bank converts at its own rate, not the central bank's. What the person saw
    arrive is the truth.
    """
    _set_rate(admin, "GEL", 30.0)
    rubles = api.default_account()
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    response = api.client.post(
        "/api/transfers",
        json={
            "fromAccountId": rubles,
            "toAccountId": lari,
            "amount": 300000,
            "toAmount": 9500,
            "date": "2026-07-05T12:00:00",
        },
    )
    assert response.status_code == 200, response.text
    legs = {t.account_id: t for t in api.snapshot().transactions}
    assert legs[lari].amount == 9500


def test_a_landing_amount_is_meaningless_within_one_currency(client: TestClient, api: Api) -> None:
    rubles = api.default_account()
    savings = api.account("Savings", AccountOptions(currency="RUB"))
    r = client.post(
        "/api/transfers",
        json={
            "fromAccountId": rubles,
            "toAccountId": savings,
            "amount": 50000,
            "toAmount": 40000,
            "date": "2026-07-05T12:00:00",
        },
    )
    assert r.status_code == 400
    assert "two currencies" in r.json()["detail"]


def test_an_unknown_statement_currency_is_rejected(client: TestClient, api: Api) -> None:
    account = api.default_account()
    rows = [{"date": "2026-07-05T10:00:00", "amount": -10000, "currency": "XYZ"}]
    r = client.post("/api/import/commit", json={"accountId": account, "rows": rows})
    assert r.status_code == 400, r.text
    assert "unknown currency" in r.json()["detail"]
    assert api.snapshot().transactions == []


def test_same_currency_transfers_still_have_equal_legs(api: Api) -> None:
    rubles = api.default_account()
    savings = api.account("Savings", AccountOptions(currency="RUB"))
    api.transfer(rubles, savings, 50000)
    legs = {t.account_id: t.amount for t in api.snapshot().transactions}
    assert legs[rubles] == -50000
    assert legs[savings] == 50000


def test_auto_detection_never_pairs_two_currencies(client: TestClient, api: Api) -> None:
    """
    Avoid matching equal amounts in different currencies.

    Same day, same magnitude, opposite signs, different accounts — the only
    thing keeping these apart is that they are not the same money.
    """
    rubles = api.default_account()
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    api.tx(
        "2026-07-05T10:00:00", -10000, TransactionOptions(account_id=rubles, description="Перевод")
    )
    api.tx("2026-07-05T11:00:00", 10000, TransactionOptions(account_id=lari, description="Перевод"))
    assert client.post("/api/transfers/detect").json() == {"merged": [], "suggested": 0}


def test_moving_a_transaction_does_not_re_denominate_it(client: TestClient, api: Api) -> None:
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    tx = api.tx("2026-07-05T10:00:00", -10000, TransactionOptions(account_id=lari))
    moved = client.patch(f"/api/transactions/{tx}", json={"accountId": api.default_account()})
    assert moved.status_code == 200, moved.text
    assert api.tx_by(tx).currency == "GEL"


def test_changing_an_account_currency_leaves_its_history_alone(
    client: TestClient, api: Api
) -> None:
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    old = api.tx("2026-07-05T10:00:00", -10000, TransactionOptions(account_id=lari))
    changed = client.patch(f"/api/accounts/{lari}", json={"currency": "USD"})
    assert changed.status_code == 200, changed.text
    fresh = api.tx("2026-07-06T10:00:00", -20000, TransactionOptions(account_id=lari))
    assert api.tx_by(old).currency == "GEL"
    assert api.tx_by(fresh).currency == "USD"


def test_a_reconcile_adjustment_is_posted_in_the_account_currency(
    client: TestClient, api: Api
) -> None:
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    groceries = api.category("Groceries", api.group("Needs"))
    api.tx(
        "2026-07-05T10:00:00", -10000, TransactionOptions(account_id=lari, category_id=groceries)
    )
    r = client.post(f"/api/accounts/{lari}/reconcile", json={"actualBalance": -15000})
    assert r.status_code == 200, r.text
    adjustment = next(
        t for t in api.snapshot().transactions if t.account_id == lari and t.source == "adjustment"
    )
    assert adjustment.currency == "GEL"
    assert adjustment.amount == -5000


def test_reconcile_converts_transaction_overrides_to_account_currency(
    admin: TestClient, api: Api
) -> None:
    """A USD row on a GEL account contributes its GEL value, not its raw number."""
    _set_rate(admin, "GEL", 30.0)
    _set_rate(admin, "USD", 90.0)
    lari = api.account("Lari", AccountOptions(currency="GEL"))
    groceries = api.category("Groceries", api.group("Needs"))
    api.tx(
        "2026-07-05T10:00:00",
        -10000,
        TransactionOptions(account_id=lari, category_id=groceries, currency="USD"),
    )

    response = admin.post(f"/api/accounts/{lari}/reconcile", json={"actualBalance": -35000})

    assert response.status_code == 200, response.text
    assert response.json()["delta"] == -5000
    adjustment = next(
        t for t in api.snapshot().transactions if t.account_id == lari and t.source == "adjustment"
    )
    assert adjustment.currency == "GEL"
    assert adjustment.amount == -5000


def test_an_unknown_account_currency_is_rejected(client: TestClient) -> None:
    r = client.post("/api/accounts", json={"name": "Dogecoin", "currency": "DOGE"})
    assert r.status_code == 400


@pytest.mark.parametrize("received", [0, -1])
def test_cross_currency_transfer_rejects_nonpositive_received_amount(
    api: Api,
    client: TestClient,
    received: int,
) -> None:
    account = api.account("Foreign", AccountOptions(currency="USD"))
    response = client.post(
        "/api/transfers",
        json={
            "fromAccountId": api.default_account(),
            "toAccountId": account,
            "amount": 100,
            "toAmount": received,
            "date": "2026-07-01T12:00:00",
        },
    )
    assert response.status_code == 422
    assert api.snapshot().transactions == []


def test_transfer_without_historical_rate_returns_actionable_error(
    api: Api,
    client: TestClient,
) -> None:
    account = api.account("Foreign", AccountOptions(currency="USD"))
    response = client.post(
        "/api/transfers",
        json={
            "fromAccountId": api.default_account(),
            "toAccountId": account,
            "amount": 100,
            "date": "2020-01-01T12:00:00",
        },
    )
    assert response.status_code == 400
    assert "state the amount that arrived" in response.json()["detail"]
    assert api.snapshot().transactions == []
