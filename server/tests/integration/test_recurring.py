from datetime import date, timedelta

from app.routers import recurring


def test_recurring_template_materializes_due_transaction_once(api, client):
    expenses = api.group("Expenses")
    rent = api.category("Rent", expenses)
    account = api.default_account()
    today = date.today().isoformat()

    response = client.post(
        "/api/recurring",
        json={
            "accountId": account,
            "categoryId": rent,
            "payee": "Landlord",
            "description": "Apartment rent",
            "amount": -100_000,
            "frequency": "monthly",
            "startDate": today,
            "autoCreate": True,
        },
    )
    assert response.status_code == 200

    first = client.get("/api/recurring").json()
    second = client.get("/api/recurring").json()
    assert len(first["createdTransactionIds"]) == 1
    assert second["createdTransactionIds"] == []
    transaction = api.tx_by(first["createdTransactionIds"][0])
    assert transaction["amount"] == -100_000
    assert transaction["categoryId"] == rent
    assert transaction["description"] == "Landlord"
    assert transaction["comment"] == "Apartment rent"
    assert transaction["source"] == "recurring"


def test_bank_import_reconciles_materialized_occurrence(api, client):
    expenses = api.group("Expenses")
    rent = api.category("Rent", expenses)
    account = api.default_account()
    today = date.today().isoformat()
    client.post(
        "/api/recurring",
        json={
            "accountId": account,
            "categoryId": rent,
            "payee": "Landlord",
            "amount": -100_000,
            "frequency": "monthly",
            "startDate": today,
            "autoCreate": True,
        },
    )
    synthetic_id = client.get("/api/recurring").json()["createdTransactionIds"][0]

    imported = client.post(
        "/api/import/commit",
        json={
            "accountId": account,
            "rows": [
                {
                    "date": f"{today}T09:34:12",
                    "amount": -100_000,
                    "description": "ARENDA KVARTIRY / SBP",
                    "bank_category": "Housing",
                    "mcc": "",
                }
            ],
        },
    )

    assert imported.status_code == 200
    assert imported.json()["inserted"] == 1
    transaction = api.tx_by(synthetic_id)
    assert transaction["description"] == "ARENDA KVARTIRY / SBP"
    assert transaction["source"] == "import"
    assert transaction["categoryId"] == rent
    assert client.get("/api/transactions").json()["total"] == 1


def test_recurring_template_validates_ownership_and_can_be_deleted(api, client):
    income = api.group("Income", "income")
    salary = api.category("Salary", income)
    body = {
        "accountId": api.default_account(),
        "categoryId": salary,
        "description": "Invalid rent",
        "amount": -1_000,
        "frequency": "weekly",
        "startDate": date.today().isoformat(),
    }
    assert client.post("/api/recurring", json=body).status_code == 400

    body.update({"amount": 1_000, "description": "Salary"})
    created = client.post("/api/recurring", json=body)
    assert created.status_code == 200
    recurring_id = created.json()["id"]
    assert client.delete(f"/api/recurring/{recurring_id}").status_code == 200
    assert client.delete(f"/api/recurring/{recurring_id}").status_code == 404


def test_manual_schedule_returns_a_due_reminder_without_creating_transaction(api, client):
    response = client.post(
        "/api/recurring",
        json={
            "accountId": api.default_account(),
            "description": "Review subscription",
            "amount": -1_000,
            "frequency": "monthly",
            "startDate": date.today().isoformat(),
            "autoCreate": False,
        },
    )
    recurring_id = response.json()["id"]

    first = client.get("/api/recurring").json()
    second = client.get("/api/recurring").json()

    assert first["createdTransactionIds"] == []
    assert first["dueReminderIds"] == [recurring_id]
    assert second["dueReminderIds"] == []


def test_monthly_schedule_keeps_original_month_end_anchor():
    due = date(2025, 1, 31)
    due = recurring._advance(due, "monthly", 1, anchor_day=31, anchor_is_month_end=True)
    assert due == date(2025, 2, 28)
    assert recurring._advance(due, "monthly", 1, anchor_day=31, anchor_is_month_end=True) == date(
        2025, 3, 31
    )


def test_materialization_caps_backlog_per_request(api, client, monkeypatch):
    monkeypatch.setattr(recurring, "MAX_MATERIALIZED_OCCURRENCES", 2)
    response = client.post(
        "/api/recurring",
        json={
            "accountId": api.default_account(),
            "description": "Daily expense",
            "amount": -100,
            "frequency": "daily",
            "startDate": (date.today() - timedelta(days=3)).isoformat(),
            "autoCreate": True,
        },
    )
    assert response.status_code == 200

    first = client.get("/api/recurring").json()
    second = client.get("/api/recurring").json()

    assert len(first["createdTransactionIds"]) == 2
    assert first["materializationTruncated"] is True
    assert len(second["createdTransactionIds"]) == 2
    assert second["materializationTruncated"] is False
