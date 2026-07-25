import pytest
from conftest import login_as

pytestmark = pytest.mark.integration

ADMIN_EMAIL = "boss@example.com"


def _make_admin(client, monkeypatch, email=ADMIN_EMAIL):
    monkeypatch.setenv("MONORI_ADMIN_EMAILS", email)
    return login_as(client, email)


def _sql(client, sql, confirm=False):
    return client.post("/api/admin/sql", json={"sql": sql, "confirmWrite": confirm})


def test_sql_console_rejects_non_admin(client):
    assert _sql(client, "SELECT 1").status_code == 403


def test_select_returns_columns_rows_and_timing(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    r = _sql(anon, "SELECT 1 AS one, 'two' AS two")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "read"
    assert body["columns"] == ["one", "two"]
    assert body["rows"] == [[1, "two"]]
    assert body["rowCount"] == 1
    assert body["truncated"] is False
    assert body["elapsedMs"] >= 0


def test_select_over_real_tables_sees_every_user(anon, monkeypatch):
    anon.headers.update(login_as(anon, "someone@example.com"))
    anon.headers.clear()
    anon.headers.update(_make_admin(anon, monkeypatch))
    rows = _sql(anon, "SELECT email FROM users ORDER BY email").json()["rows"]
    assert ["someone@example.com"] in rows


def test_reads_are_capped_and_flagged(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    body = _sql(
        anon,
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 1500)"
        " SELECT i FROM n",
    ).json()
    assert body["rowCount"] == 1000
    assert len(body["rows"]) == 1000
    assert body["truncated"] is True


def test_write_without_confirmation_is_rolled_back(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    before = _sql(anon, "SELECT COUNT(*) FROM activity_events").json()["rows"][0][0]
    r = _sql(anon, "DELETE FROM activity_events")
    assert r.status_code == 400
    assert "confirmation" in r.json()["detail"]
    # +1: the counting SELECT audited itself before the DELETE looked at the table
    assert f"affected {before + 1} rows" in r.json()["detail"]
    # the rejected delete left the table alone; the two SELECTs around it added
    # one audit row each, which is what a console statement is supposed to do
    assert _sql(anon, "SELECT COUNT(*) FROM activity_events").json()["rows"][0][0] > before


def test_confirmed_write_applies_and_reports_row_count(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    uid = anon.get("/api/auth/me").json()["id"]
    r = _sql(anon, f"UPDATE users SET is_admin=1 WHERE id={uid}", confirm=True)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "kind": "write",
        "columns": [],
        "rows": [],
        "rowCount": 1,
        "truncated": False,
        "elapsedMs": r.json()["elapsedMs"],
    }


def test_write_disguised_as_a_query_still_needs_confirmation(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    r = _sql(
        anon,
        "WITH doomed AS (SELECT id FROM users)"
        " DELETE FROM activity_events WHERE user_id IN (SELECT id FROM doomed)",
    )
    assert r.status_code == 400
    assert "confirmation" in r.json()["detail"]


def test_ddl_rolls_back_without_confirmation(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    assert _sql(anon, "CREATE TABLE scratch (id INTEGER)").status_code == 400
    assert _sql(anon, "SELECT * FROM scratch").status_code == 400  # never created

    assert _sql(anon, "CREATE TABLE scratch (id INTEGER)", confirm=True).status_code == 200
    assert _sql(anon, "SELECT * FROM scratch").json()["rows"] == []


def test_sqlite_errors_come_back_verbatim(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    r = _sql(anon, "SELECT * FROM nope")
    assert r.status_code == 400
    assert r.json()["detail"] == "no such table: nope"


def test_empty_and_multiple_statements_are_refused(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    assert _sql(anon, "   ").status_code == 400
    r = _sql(anon, "SELECT 1; SELECT 2")
    assert r.status_code == 400
    assert "one statement" in r.json()["detail"]


def test_a_timed_out_statement_is_refused_and_still_audited(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    monkeypatch.setattr("app.routers.admin_sql.QUERY_TIMEOUT_S", 0.05)
    runaway = (
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 50000000)"
        " SELECT COUNT(*) FROM n"
    )
    r = _sql(anon, runaway)
    assert r.status_code == 400
    assert "interrupted" in r.json()["detail"]

    # the deadline must not have leaked past the query it guarded: the audit row
    # is written on the same connection, right after the interrupt
    monkeypatch.setattr("app.routers.admin_sql.QUERY_TIMEOUT_S", 15.0)
    audited = _sql(anon, "SELECT detail FROM activity_events WHERE kind='admin_sql_failed'").json()[
        "rows"
    ]
    assert [runaway] in audited


def test_a_huge_text_cell_comes_back_cut(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    body = _sql(anon, "SELECT hex(zeroblob(50000)) AS big").json()
    (value,) = body["rows"][0]
    assert value.endswith(" chars)")
    assert len(value) < 5000


def test_every_statement_is_audited(anon, monkeypatch):
    anon.headers.update(_make_admin(anon, monkeypatch))
    _sql(anon, "SELECT 1")
    _sql(anon, "DELETE FROM feature_usage")
    _sql(anon, "SELECT * FROM nope")
    rows = _sql(
        anon,
        "SELECT kind, detail FROM activity_events WHERE kind LIKE 'admin_sql%' ORDER BY id",
    ).json()["rows"]
    assert rows[:3] == [
        ["admin_sql", "SELECT 1"],
        ["admin_sql_rejected", "DELETE FROM feature_usage"],
        ["admin_sql_failed", "SELECT * FROM nope"],
    ]
