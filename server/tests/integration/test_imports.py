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


def test_import_commit_double_submit_is_idempotent(api, client):
    rows = api.preview(api.statement)
    first = client.post(
        "/api/import/commit", json={"accountId": api.default_account(), "rows": rows}
    ).json()
    assert first == {"inserted": 2, "skipped": 0}
    resubmit = client.post(
        "/api/import/commit", json={"accountId": api.default_account(), "rows": rows}
    ).json()
    assert resubmit == {"inserted": 0, "skipped": 2}
    assert client.get("/api/transactions").json()["total"] == 2


def test_import_commit_skips_only_the_first_n_already_stored(api, client):
    """Skip as many identical rows as already exist in the DB, insert the rest —
    a fresh statement's own repeats are legitimate, only re-imports are skipped."""
    r0 = api.preview(api.statement)[0]

    # fresh DB: three identical rows are all genuinely new
    assert client.post(
        "/api/import/commit", json={"accountId": api.default_account(), "rows": [r0, r0, r0]}
    ).json() == {
        "inserted": 3,
        "skipped": 0,
    }
    assert client.get("/api/transactions").json()["total"] == 3

    # DB now holds 3; the same three are all skipped
    assert client.post(
        "/api/import/commit", json={"accountId": api.default_account(), "rows": [r0, r0, r0]}
    ).json() == {
        "inserted": 0,
        "skipped": 3,
    }

    # DB holds 3; five identical -> two beyond the stored three are inserted
    assert client.post(
        "/api/import/commit", json={"accountId": api.default_account(), "rows": [r0] * 5}
    ).json() == {
        "inserted": 2,
        "skipped": 3,
    }
    assert client.get("/api/transactions").json()["total"] == 5


def test_import_commit_keeps_category(api, client):
    g = api.group("Expenses")
    cat = api.category("Groceries", g)
    rows = api.preview(api.statement)
    rows[0]["categoryId"] = cat
    client.post("/api/import/commit", json={"accountId": api.default_account(), "rows": rows})
    imported = client.get(f"/api/transactions?categoryId={cat}").json()
    assert imported["total"] == 1 and imported["rows"][0]["source"] == "import"


def test_commit_rejects_unknown_account(client):
    r = client.post("/api/import/commit", json={"accountId": 999, "rows": []})
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown account"
