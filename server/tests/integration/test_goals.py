import pytest
from fastapi.testclient import TestClient

from tests.conftest import Api

pytestmark = pytest.mark.integration


def test_goal_crud_accepts_spending_and_archive_preserves_history(
    api: Api,
    client: TestClient,
) -> None:
    group = api.group("Goals", kind="goal")
    created = client.post(
        "/api/categories",
        json={
            "name": "Camera",
            "groupId": group,
            "goalTarget": 100_000,
            "goalTargetDate": "2026-12-31",
        },
    )
    assert created.status_code == 200, created.text
    goal = created.json()["id"]
    client.put(
        "/api/budgets",
        json={"categoryId": goal, "year": 2026, "month": 1, "amount": 30_000},
    )
    purchase = api.tx("2026-02-20T10:00:00", -40_000, categoryId=goal)
    client.put(
        "/api/budgets",
        json={"categoryId": goal, "year": 2026, "month": 2, "amount": 20_000},
    )

    snap = api.snapshot()
    cat = next(category for category in snap.categories if category.id == goal)
    assert cat.goalTarget == 100_000
    assert cat.goalStatus == "active"
    assert cat.goalTargetDate == "2026-12-31"

    archived = client.post(f"/api/categories/{goal}/archive-goal", json={})
    assert archived.status_code == 200, archived.text
    snap = api.snapshot()
    cat = next(category for category in snap.categories if category.id == goal)
    assert cat.archived is True
    assert cat.goalStatus == "archived"
    assert sum(budget.amount for budget in snap.budgets if budget.categoryId == goal) == 50_000
    purchase_row = next(
        transaction for transaction in snap.transactions if transaction.id == purchase
    )
    assert purchase_row.categoryId == goal


def test_goal_requires_target(api: Api, client: TestClient) -> None:
    group = api.group("Goals", kind="goal")
    r = client.post("/api/categories", json={"name": "Trip", "groupId": group})
    assert r.status_code == 400


def test_moving_goal_to_expense_group_clears_goal_metadata(api: Api, client: TestClient) -> None:
    goals = api.group("Goals", kind="goal")
    expenses = api.group("Expenses")
    created = client.post(
        "/api/categories",
        json={
            "name": "Camera",
            "groupId": goals,
            "goalTarget": 100_000,
            "goalTargetDate": "2026-12-31",
        },
    )
    goal = created.json()["id"]

    moved = client.patch(f"/api/categories/{goal}", json={"groupId": expenses})
    assert moved.status_code == 200, moved.text
    category = next(category for category in api.snapshot().categories if category.id == goal)
    assert category.goalTarget is None
    assert category.goalStatus is None
    assert category.goalTargetDate is None
