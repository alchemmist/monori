import os
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    monkeypatch.setenv("MONORI_DB", db_path)
    import app.db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app

    c = dbmod.connect(db_path)
    c.execute("INSERT INTO category_groups (id, name, sort, kind) VALUES (1,'Fixed',1,'expense')")
    c.execute("INSERT INTO category_groups (id, name, sort, kind) VALUES (2,'Inflow',2,'income')")
    c.execute("INSERT INTO categories (id, group_id, name, keywords, sort) VALUES (1,1,'Groceries','Пятёрочка',1)")
    c.execute("INSERT INTO categories (id, group_id, name, keywords, sort) VALUES (2,1,'Taxi','Taxi',2)")
    from app.importer import tx_hash

    c.execute(
        "INSERT INTO transactions (date, amount, description, category_id, hash) "
        "VALUES ('2026-01-05T10:00:00', -10000, 'Пятёрочка', 1, ?)",
        (tx_hash("2026-01-05T10:00:00", -10000, "Пятёрочка"),),
    )
    c.execute("INSERT INTO budgets (category_id, year, month, amount) VALUES (1, 2026, 1, 50000)")
    c.commit()
    c.close()
    return TestClient(fastapi_app)


def test_snapshot(client):
    s = client.get("/api/snapshot").json()
    assert len(s["groups"]) == 2
    assert len(s["categories"]) == 2
    assert len(s["transactions"]) == 1
    assert s["budgets"] == [{"categoryId": 1, "year": 2026, "month": 1, "amount": 50000}]


def test_budget_upsert_and_delete(client):
    r = client.put("/api/budgets", json={"categoryId": 1, "year": 2026, "month": 2, "amount": 70000})
    assert r.status_code == 200
    assert len(client.get("/api/snapshot").json()["budgets"]) == 2
    client.put("/api/budgets", json={"categoryId": 1, "year": 2026, "month": 2, "amount": 0})
    assert len(client.get("/api/snapshot").json()["budgets"]) == 1


def test_category_crud_and_delete_with_reassign(client):
    r = client.post("/api/categories", json={"name": "Coffee", "groupId": 1, "keywords": "Cofix"})
    cid = r.json()["id"]
    assert client.post("/api/categories", json={"name": "Coffee", "groupId": 1}).status_code == 409

    client.patch(f"/api/categories/{cid}", json={"keywords": "Cofix|Дринкит"})

    # deleting category 1 with reassign to Coffee: tx moves, budget rows die, nothing shifts
    r = client.delete(f"/api/categories/1?reassignTo={cid}")
    assert r.status_code == 200
    s = client.get("/api/snapshot").json()
    assert [c["name"] for c in s["categories"]] == ["Taxi", "Coffee"]
    assert s["transactions"][0]["categoryId"] == cid
    assert s["budgets"] == []


def test_delete_category_without_reassign_uncategorizes(client):
    client.delete("/api/categories/1")
    s = client.get("/api/snapshot").json()
    assert s["transactions"][0]["categoryId"] is None


def test_import_preview_and_commit(client):
    text = (
        "05.01.2026 10:00:00\t05.01.2026\t*1\tOK\t-100,00\tRUB\t-100,00\tRUB\t\t"
        "Супермаркеты\t5411\tПятёрочка\t0\t0\t-100,00\n"
        "06.01.2026 11:00:00\t06.01.2026\t*1\tOK\t-200,00\tRUB\t-200,00\tRUB\t\t"
        "Супермаркеты\t5411\tПятёрочка\t0\t0\t-200,00\n"
    )
    prev = client.post("/api/import/preview", json={"text": text}).json()
    assert len(prev["rows"]) == 2
    first = prev["rows"][0]
    assert first["duplicate"] is True  # same date/amount/description as seeded tx
    assert first["categoryId"] == 1
    assert prev["rows"][1]["duplicate"] is False

    fresh = [r for r in prev["rows"] if not r["duplicate"]]
    r = client.post("/api/import/commit", json={"rows": fresh}).json()
    assert r["inserted"] == 1
    assert len(client.get("/api/snapshot").json()["transactions"]) == 2


def test_tx_patch(client):
    client.patch("/api/transactions/1", json={"categoryId": 2})
    s = client.get("/api/snapshot").json()
    assert s["transactions"][0]["categoryId"] == 2
    assert client.patch("/api/transactions/999", json={"comment": "x"}).status_code == 404
