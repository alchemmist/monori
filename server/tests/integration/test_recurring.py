from datetime import date


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
