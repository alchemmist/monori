import pytest

pytestmark = pytest.mark.integration


def test_import_preview_categorizes_and_flags_errors(api, client):
    g = api.group("Expenses")
    api.category("Groceries", g, "Lenta")
    text = api.statement + "garbage line without enough columns\n"
    prev = client.post("/api/import/preview", json={"text": text}).json()
    assert len(prev["rows"]) == 2
    assert prev["rows"][0]["categoryId"] is not None
    assert prev["rows"][1]["categoryId"] is None
    assert len(prev["errors"]) == 1


def test_import_commit_dedup_within_batch_and_vs_db(api, client):
    rows = api.preview(api.statement)

    within = client.post("/api/import/commit", json={"rows": [rows[0], rows[0]]}).json()
    assert within == {"inserted": 1, "skipped": 1}
    assert client.get("/api/transactions").json()["total"] == 1

    both = client.post("/api/import/commit", json={"rows": rows}).json()
    assert both == {"inserted": 1, "skipped": 1}
    assert client.get("/api/transactions").json()["total"] == 2

    resubmit = client.post("/api/import/commit", json={"rows": rows}).json()
    assert resubmit == {"inserted": 0, "skipped": 2}


def test_import_commit_keeps_category(api, client):
    g = api.group("Expenses")
    cat = api.category("Groceries", g)
    rows = api.preview(api.statement)
    rows[0]["categoryId"] = cat
    client.post("/api/import/commit", json={"rows": rows})
    imported = client.get(f"/api/transactions?categoryId={cat}").json()
    assert imported["total"] == 1 and imported["rows"][0]["source"] == "import"
