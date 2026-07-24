import os
import sqlite3

from alembic import command

from app.db import LEGACY_REVISIONS, _alembic_config, connect

HEAD = "0008"
assert LEGACY_REVISIONS[-1] == "0006"

OLD_SCHEMA = """
CREATE TABLE category_groups (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, sort INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('income', 'expense'))
);
CREATE TABLE categories (
  id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL REFERENCES category_groups(id),
  name TEXT NOT NULL UNIQUE, keywords TEXT NOT NULL DEFAULT '',
  sort INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE transactions (
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, amount INTEGER NOT NULL,
  description TEXT NOT NULL DEFAULT '', bank_category TEXT NOT NULL DEFAULT '',
  mcc TEXT NOT NULL DEFAULT '',
  category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  comment TEXT NOT NULL DEFAULT '', hash TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'import'
);
CREATE TABLE budgets (
  category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  year INTEGER NOT NULL, month INTEGER NOT NULL, amount INTEGER NOT NULL,
  PRIMARY KEY (category_id, year, month)
);
"""


def _make_old_db(path):
    old = sqlite3.connect(path)
    old.executescript(OLD_SCHEMA)
    old.execute(
        "INSERT INTO transactions (id, date, amount, description, hash) VALUES "
        "(1, '2026-01-01T00:00:00', -100, 'a', 'h1'),"
        "(2, '2026-01-02T00:00:00', -200, 'b', 'h2')"
    )
    old.commit()
    old.close()


def _revision(conn):
    return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_migration_backfills_existing_transactions(tmp_path):
    db_path = os.path.join(tmp_path, "old.db")
    _make_old_db(db_path)

    conn = connect(db_path)
    try:
        accounts = conn.execute("SELECT id, name FROM accounts").fetchall()
        assert [a["name"] for a in accounts] == ["T-Bank"]
        default_id = accounts[0]["id"]

        rows = conn.execute("SELECT id, account_id, transfer_id FROM transactions").fetchall()
        assert len(rows) == 2
        assert all(r["account_id"] == default_id for r in rows)
        assert all(r["transfer_id"] is None for r in rows)

        cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(transactions)")}
        assert cols["account_id"]["notnull"] == 1

        icon = conn.execute("SELECT icon FROM accounts WHERE id=?", (default_id,)).fetchone()[
            "icon"
        ]
        assert icon == "wallet"
        acct_cols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
        assert {"color", "icon_image"} <= acct_cols

        assert _revision(conn) == HEAD
    finally:
        conn.close()


def test_migration_is_idempotent(tmp_path):
    db_path = os.path.join(tmp_path, "old.db")
    _make_old_db(db_path)
    connect(db_path).close()
    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2
        assert _revision(conn) == HEAD
    finally:
        conn.close()


def test_fresh_db_is_created_from_schema_sql(tmp_path):
    db_path = os.path.join(tmp_path, "fresh.db")
    conn = connect(db_path)
    try:
        tables = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {
            "category_groups",
            "categories",
            "accounts",
            "transactions",
            "budgets",
            "bank_connections",
            "import_batches",
            "users",
        } <= tables
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(transactions)")}
        assert {"account_id", "transfer_id", "batch_id"} <= cols
        acct_cols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
        assert "user_id" in acct_cols
        assert _revision(conn) == HEAD
    finally:
        conn.close()


def _describe(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = sorted(
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if r["name"] != "alembic_version" and not r["name"].startswith("sqlite_")
        )
        shape = {}
        for t in tables:
            cols = sorted(
                (r["name"], r["type"].upper(), r["notnull"], r["dflt_value"], bool(r["pk"]))
                for r in conn.execute(f"PRAGMA table_info({t})")
            )
            indexes = sorted(
                r["name"]
                for r in conn.execute(f"PRAGMA index_list({t})")
                if not r["name"].startswith("sqlite_")
            )
            shape[t] = (cols, indexes)
        return shape
    finally:
        conn.close()


def test_schema_sql_matches_migration_chain(tmp_path):
    fresh = os.path.join(tmp_path, "fresh.db")
    connect(fresh).close()

    chained = os.path.join(tmp_path, "chained.db")
    command.upgrade(_alembic_config(chained), "head")

    assert _describe(fresh) == _describe(chained)


def test_legacy_intermediate_user_version_is_adopted(tmp_path):
    db_path = os.path.join(tmp_path, "v1.db")
    command.upgrade(_alembic_config(db_path), "0002")
    raw = sqlite3.connect(db_path)
    raw.execute("DROP TABLE alembic_version")
    raw.execute("PRAGMA user_version = 1")
    raw.commit()
    raw.close()

    conn = connect(db_path)
    try:
        assert _revision(conn) == HEAD
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
        acct_cols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
        assert {"icon", "color", "icon_image"} <= acct_cols
        tables = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"bank_connections", "import_batches", "users"} <= tables
    finally:
        conn.close()


def test_upgrade_assigns_orphans_to_earliest_user(tmp_path):
    db_path = os.path.join(tmp_path, "v6.db")
    command.upgrade(_alembic_config(db_path), "0006")
    raw = sqlite3.connect(db_path)
    raw.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('a@b.co', 'h', 't')")
    raw.execute(
        "INSERT INTO accounts (name, type, currency, sort) VALUES ('Old', 'card', 'RUB', 1)"
    )
    raw.execute("INSERT INTO category_groups (name, sort, kind) VALUES ('G', 1, 'expense')")
    raw.commit()
    raw.close()

    conn = connect(db_path)
    try:
        uid = conn.execute("SELECT MIN(id) FROM users").fetchone()[0]
        assert conn.execute("SELECT user_id FROM accounts").fetchone()[0] == uid
        assert conn.execute("SELECT user_id FROM category_groups").fetchone()[0] == uid
    finally:
        conn.close()


def test_concurrent_first_connects_bootstrap_once(tmp_path, monkeypatch):
    import threading
    import time

    import app.db as dbmod

    db_path = os.path.join(tmp_path, "race.db")
    calls = []
    real_bootstrap = dbmod._bootstrap

    def slow_bootstrap(path):
        calls.append(1)
        time.sleep(0.05)
        real_bootstrap(path)

    monkeypatch.setattr(dbmod, "_bootstrap", slow_bootstrap)
    threads = [threading.Thread(target=lambda: connect(db_path).close()) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1


def test_default_account_fields(tmp_path):
    db_path = os.path.join(tmp_path, "old.db")
    _make_old_db(db_path)
    conn = connect(db_path)
    try:
        a = conn.execute(
            "SELECT name, type, currency, sort, icon, color, icon_image FROM accounts"
        ).fetchone()
        assert a["name"] == "T-Bank"
        assert a["type"] == "card"
        assert a["currency"] == "RUB"
        assert a["sort"] == 1
        assert a["icon"] == "wallet"
        assert a["color"] == "#5b6472"
        assert a["icon_image"] is None
    finally:
        conn.close()


def test_new_account_gets_column_defaults(tmp_path):
    db_path = os.path.join(tmp_path, "fresh.db")
    conn = connect(db_path)
    try:
        conn.execute("INSERT INTO accounts (name) VALUES ('Extra')")
        a = conn.execute(
            "SELECT type, currency, sort, archived, opening_balance, icon, color, icon_image"
            " FROM accounts WHERE name='Extra'"
        ).fetchone()
        assert a["type"] == "other"
        assert a["currency"] == "RUB"
        assert a["sort"] == 0
        assert a["archived"] == 0
        assert a["opening_balance"] == 0
        assert a["icon"] == "wallet"
        assert a["color"] == "#5b6472"
        assert a["icon_image"] is None
    finally:
        conn.close()


def test_connection_conversion_to_user_level(tmp_path):
    db_path = os.path.join(tmp_path, "conv.db")
    command.upgrade(_alembic_config(db_path), "0007")
    c = sqlite3.connect(db_path)
    c.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('u@e.co', 'h', 't')")
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (1, 'Card', 'card', 'RUB', 1)"
    )
    acct_id = c.execute("SELECT id FROM accounts WHERE name='Card'").fetchone()[0]
    c.execute(
        "INSERT INTO bank_connections (account_id, bank, kind, status, created_at, updated_at)"
        f" VALUES ({acct_id}, 'tbank', 'playwright', 'connected', 't1', 't2')"
    )
    c.commit()
    c.close()

    command.upgrade(_alembic_config(db_path), "head")
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    conn_row = c.execute("SELECT * FROM bank_connections").fetchone()
    assert conn_row["user_id"] == 1
    conn_cols = conn_row.keys()
    assert "account_id" not in conn_cols
    acct = c.execute("SELECT connection_id, bank_ref FROM accounts WHERE name='Card'").fetchone()
    assert acct["connection_id"] == conn_row["id"]
    assert acct["bank_ref"] == ""
    c.close()
