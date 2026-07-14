import os
import sqlite3

from app.db import MIGRATIONS, connect

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

        assert accounts[0]["name"] == "T-Bank"
        icon = conn.execute("SELECT icon FROM accounts WHERE id=?", (default_id,)).fetchone()[
            "icon"
        ]
        assert icon == "wallet"

        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
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
    finally:
        conn.close()


def test_fresh_db_has_accounts_and_account_id(tmp_path):
    db_path = os.path.join(tmp_path, "fresh.db")
    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(transactions)")}
        assert {"account_id", "transfer_id"} <= cols
    finally:
        conn.close()
