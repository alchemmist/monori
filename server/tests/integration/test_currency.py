import httpx
import pytest

from app.rates import store_rates

pytestmark = pytest.mark.integration

RATE_DAY = "2026-07-01"


def _set_rate(client, code, rub_per_unit, day=RATE_DAY):
    r = client.put(f"/api/rates/{code}", json={"day": day, "rubPerUnit": rub_per_unit})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_transaction_inherits_its_account_currency(api):
    lari = api.account("Lari", currency="GEL")
    tx = api.tx("2026-07-05T10:00:00", -10000, accountId=lari)
    assert api.tx_by(tx)["currency"] == "GEL"


def test_a_transaction_may_name_a_currency_of_its_own(api):
    """
    A ruble card used abroad bills in rubles, but a foreign-currency wallet on
    the same account is a real thing — the row says what it was, not the account.
    """
    rubles = api.default_account()
    tx = api.tx("2026-07-05T10:00:00", -10000, accountId=rubles, currency="usd")
    assert api.tx_by(tx)["currency"] == "USD"


def test_an_unknown_currency_is_rejected(client, api):
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


def test_base_amount_is_the_row_converted_into_the_reporting_currency(client, api):
    _set_rate(client, "GEL", 30.0)
    lari = api.account("Lari", currency="GEL")
    tx = api.tx("2026-07-05T10:00:00", -10000, accountId=lari)
    row = api.tx_by(tx)
    assert row["amount"] == -10000
    assert row["baseAmount"] == -300000


def test_base_amount_of_the_reporting_currency_is_the_amount_itself(api):
    tx = api.tx("2026-07-05T10:00:00", -12345)
    row = api.tx_by(tx)
    assert row["baseAmount"] == row["amount"] == -12345


def test_switching_the_reporting_currency_reprices_the_ledger(client, api):
    _set_rate(client, "GEL", 30.0)
    _set_rate(client, "USD", 90.0)
    lari = api.account("Lari", currency="GEL")
    tx = api.tx("2026-07-05T10:00:00", -30000, accountId=lari)
    assert api.tx_by(tx)["baseAmount"] == -900000

    r = client.patch("/api/auth/me", json={"baseCurrency": "USD"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["baseCurrency"] == "USD"
    assert r.json()["repriced"] >= 1
    # 300.00 GEL = 9000 RUB = 100.00 USD
    assert api.tx_by(tx)["baseAmount"] == -10000
    # the row itself is untouched — only what it is expressed in changed
    assert api.tx_by(tx)["amount"] == -30000
    assert api.snapshot()["baseCurrency"] == "USD"


def test_switching_to_an_unknown_reporting_currency_is_rejected(client):
    assert client.patch("/api/auth/me", json={"baseCurrency": "XYZ"}).status_code == 400


def test_correcting_a_rate_reprices_what_it_priced(client, api):
    _set_rate(client, "GEL", 30.0)
    lari = api.account("Lari", currency="GEL")
    tx = api.tx("2026-07-05T10:00:00", -10000, accountId=lari)
    assert api.tx_by(tx)["baseAmount"] == -300000
    assert _set_rate(client, "GEL", 40.0)["repriced"] == 1
    assert api.tx_by(tx)["baseAmount"] == -400000


def test_refresh_pulls_the_feed_and_reprices(client, api, monkeypatch):
    from app.routers import rates as rates_router

    lari = api.account("Lari", currency="GEL")
    tx = api.tx("2026-07-05T10:00:00", -10000, accountId=lari)

    def fake_refresh(c, day=None, client=None):
        return store_rates(c, day or RATE_DAY, {"GEL": 25.0})

    monkeypatch.setattr(rates_router, "refresh", fake_refresh)
    monkeypatch.setattr(rates_router, "backfill", lambda c, days: days)

    body = client.post("/api/rates/refresh?days=3").json()
    assert body["stored"] == 1
    assert body["days"] == 4
    assert body["repriced"] == 1
    assert api.tx_by(tx)["baseAmount"] == -250000


def test_refresh_reports_an_unreachable_feed_as_a_bad_gateway(client, monkeypatch):
    from app.routers import rates as rates_router

    def explode(c, day=None, client=None):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(rates_router, "refresh", explode)
    r = client.post("/api/rates/refresh")
    assert r.status_code == 502
    assert "rate feed" in r.json()["detail"]


def test_a_rate_may_not_be_set_for_the_pivot_itself(client):
    r = client.put("/api/rates/RUB", json={"rubPerUnit": 2.0})
    assert r.status_code == 400


def test_rates_endpoint_serves_the_registry_and_the_quotes(client):
    body = client.get("/api/rates").json()
    assert body["baseCurrency"] == "RUB"
    codes = {c["code"] for c in body["currencies"]}
    assert {"RUB", "USD", "GEL"} <= codes
    assert {r["code"] for r in body["rates"]} == codes
    assert all(c["minorUnits"] == 2 for c in body["currencies"])


def test_two_currencies_with_the_same_amount_are_not_each_other_duplicate(client, api):
    """
    The dedup fingerprint covers the currency: 100 lari and 100 rubles on the
    same day with the same description are different money, and an import that
    collapsed one into the other would lose it silently.
    """
    account = api.default_account()
    api.tx("2026-07-05T10:00:00", -10000, accountId=account, description="Coffee")
    api.tx("2026-07-05T10:00:00", -10000, accountId=account, description="Coffee", currency="GEL")
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
    # the ruble row is already there and is skipped; the lari one never matched it
    assert rows == {
        "inserted": 0,
        "skipped": 1,
        "transfersMerged": 0,
        "transfersSuggested": 0,
    }


def test_a_transfer_between_two_currencies_carries_each_leg_in_its_own(client, api):
    _set_rate(client, "GEL", 30.0)
    rubles = api.default_account()
    lari = api.account("Lari", currency="GEL")
    api.transfer(rubles, lari, 300000, date="2026-07-05T12:00:00")
    legs = {t["accountId"]: t for t in api.snapshot()["transactions"]}
    assert legs[rubles]["amount"] == -300000
    assert legs[rubles]["currency"] == "RUB"
    # 3000.00 RUB at 30 RUB per lari is 100.00 lari
    assert legs[lari]["amount"] == 10000
    assert legs[lari]["currency"] == "GEL"
    # both legs are worth the same in the reporting currency
    assert legs[lari]["baseAmount"] == -legs[rubles]["baseAmount"]


def test_a_stated_landing_amount_beats_the_published_rate(client, api):
    """
    A bank converts at its own rate, not the central bank's. What the person saw
    arrive is the truth.
    """
    _set_rate(client, "GEL", 30.0)
    rubles = api.default_account()
    lari = api.account("Lari", currency="GEL")
    api.transfer(rubles, lari, 300000, date="2026-07-05T12:00:00", toAmount=9500)
    legs = {t["accountId"]: t for t in api.snapshot()["transactions"]}
    assert legs[lari]["amount"] == 9500


def test_same_currency_transfers_still_have_equal_legs(api):
    rubles = api.default_account()
    savings = api.account("Savings", currency="RUB")
    api.transfer(rubles, savings, 50000)
    legs = {t["accountId"]: t["amount"] for t in api.snapshot()["transactions"]}
    assert legs[rubles] == -50000
    assert legs[savings] == 50000


def test_auto_detection_never_pairs_two_currencies(client, api):
    """
    Same day, same magnitude, opposite signs, different accounts — the only
    thing keeping these apart is that they are not the same money.
    """
    rubles = api.default_account()
    lari = api.account("Lari", currency="GEL")
    api.tx("2026-07-05T10:00:00", -10000, accountId=rubles, description="Перевод")
    api.tx("2026-07-05T11:00:00", 10000, accountId=lari, description="Перевод")
    assert client.post("/api/transfers/detect").json() == {"merged": [], "suggested": 0}


def test_moving_a_transaction_does_not_re_denominate_it(client, api):
    lari = api.account("Lari", currency="GEL")
    tx = api.tx("2026-07-05T10:00:00", -10000, accountId=lari)
    moved = client.patch(f"/api/transactions/{tx}", json={"accountId": api.default_account()})
    assert moved.status_code == 200, moved.text
    assert api.tx_by(tx)["currency"] == "GEL"


def test_changing_an_account_currency_leaves_its_history_alone(client, api):
    lari = api.account("Lari", currency="GEL")
    old = api.tx("2026-07-05T10:00:00", -10000, accountId=lari)
    changed = client.patch(f"/api/accounts/{lari}", json={"currency": "USD"})
    assert changed.status_code == 200, changed.text
    fresh = api.tx("2026-07-06T10:00:00", -20000, accountId=lari)
    assert api.tx_by(old)["currency"] == "GEL"
    assert api.tx_by(fresh)["currency"] == "USD"


def test_a_reconcile_adjustment_is_posted_in_the_account_currency(client, api):
    lari = api.account("Lari", currency="GEL")
    api.tx("2026-07-05T10:00:00", -10000, accountId=lari)
    r = client.post(f"/api/accounts/{lari}/reconcile", json={"actualBalance": -15000})
    assert r.status_code == 200, r.text
    adjustment = next(
        t
        for t in api.snapshot()["transactions"]
        if t["accountId"] == lari and t["source"] == "adjustment"
    )
    assert adjustment["currency"] == "GEL"
    assert adjustment["amount"] == -5000


def test_an_unknown_account_currency_is_rejected(client):
    r = client.post("/api/accounts", json={"name": "Dogecoin", "currency": "DOGE"})
    assert r.status_code == 400
