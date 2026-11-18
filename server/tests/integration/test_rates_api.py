# Copyright (c) 2026
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from monori.server.tests.conftest import login_as

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("value", ["Infinity", "-Infinity", "NaN"])
def test_manual_rate_rejects_nonfinite_input(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MONORI_ADMIN_EMAILS", "tester@example.com")
    client.headers.update(login_as(client, "tester@example.com"))
    response = client.put("/api/rates/USD", json={"rubPerUnit": value, "day": "2020-01-01"})
    assert response.status_code == 422, response.text
    with sqlite3.connect(os.environ["MONORI_DB"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0] == 0


@pytest.fixture
def admin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MONORI_ADMIN_EMAILS", "tester@example.com")
    client.headers.update(login_as(client, "tester@example.com"))
    return client


@pytest.fixture
def historical_ledger(client: TestClient) -> None:
    account_id = client.get("/api/accounts").json()[0]["id"]
    with sqlite3.connect(os.environ["MONORI_DB"]) as connection:
        connection.executemany(
            "INSERT INTO transactions (date, amount, currency, base_amount, account_id, hash)"
            " VALUES ('2020-01-02', -100, ?, -100, ?, ?)",
            [(code, account_id, code) for code in ("USD", "GEL")],
        )


@pytest.mark.usefixtures("historical_ledger")
def test_batch_repairs_multiple_missing_quotes_atomically(admin: TestClient) -> None:
    single = admin.put("/api/rates/USD", json={"day": "2020-01-01", "rubPerUnit": 90})
    assert single.status_code == 400
    with sqlite3.connect(os.environ["MONORI_DB"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0] == 0
        assert connection.execute("SELECT DISTINCT base_amount FROM transactions").fetchall() == [
            (-100,)
        ]
    repaired = admin.put(
        "/api/rates",
        json={
            "rates": [
                {"code": "USD", "day": "2020-01-01", "rubPerUnit": 90},
                {"code": "GEL", "day": "2020-01-01", "rubPerUnit": 30},
            ]
        },
    )
    assert repaired.status_code == 200, repaired.text
    assert repaired.json() == {"stored": 2, "repriced": 2}
    snapshot = admin.get("/api/snapshot")
    assert snapshot.status_code == 200, snapshot.text
    amounts = {row["currency"]: row["baseAmount"] for row in snapshot.json()["transactions"]}
    assert amounts == {"USD": -9000, "GEL": -3000}


@pytest.mark.usefixtures("historical_ledger")
def test_incomplete_batch_rolls_back_rates_and_repricing(admin: TestClient) -> None:
    response = admin.put(
        "/api/rates",
        json={"rates": [{"code": "USD", "day": "2020-01-01", "rubPerUnit": 90}]},
    )
    assert response.status_code == 400
    with sqlite3.connect(os.environ["MONORI_DB"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0] == 0
        assert connection.execute("SELECT DISTINCT base_amount FROM transactions").fetchall() == [
            (-100,)
        ]


@pytest.mark.parametrize("code", ["RUB", "UNKNOWN"])
def test_invalid_batch_currency_does_not_write_any_quotes(admin: TestClient, code: str) -> None:
    response = admin.put(
        "/api/rates",
        json={
            "rates": [
                {"code": "USD", "rubPerUnit": 90},
                {"code": code, "rubPerUnit": 30},
            ]
        },
    )
    assert response.status_code == 400
    with sqlite3.connect(os.environ["MONORI_DB"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0] == 0


@pytest.mark.parametrize("value", ["Infinity", "-Infinity", "NaN"])
def test_batch_rejects_nonfinite_quote(admin: TestClient, value: str) -> None:
    response = admin.put("/api/rates", json={"rates": [{"code": "USD", "rubPerUnit": value}]})
    assert response.status_code == 422, response.text


def test_batch_requires_admin(client: TestClient) -> None:
    response = client.put("/api/rates", json={"rates": [{"code": "USD", "rubPerUnit": 90}]})
    assert response.status_code == 403


def test_batch_requires_at_least_one_quote(admin: TestClient) -> None:
    response = admin.put("/api/rates", json={"rates": []})
    assert response.status_code == 422


@pytest.mark.parametrize("path", ["/api/rates/USD", "/api/rates"])
@pytest.mark.parametrize("number", ["1e400", "-1e400", "NaN"])
def test_raw_nonfinite_json_returns_a_serializable_client_error(
    admin: TestClient, path: str, number: str
) -> None:
    quote = '{"code":"USD","rubPerUnit":' + number + "}"
    content = (
        '{"rubPerUnit":' + number + "}" if path.endswith("USD") else '{"rates":[' + quote + "]}"
    )
    response = admin.put(path, content=content, headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert response.json() == {"detail": "rubPerUnit must be finite"}
    with sqlite3.connect(os.environ["MONORI_DB"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0] == 0
