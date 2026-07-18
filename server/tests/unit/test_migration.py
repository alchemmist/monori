import os
import sqlite3

from app.db import (
    MIGRATIONS,
    _migrate_account_color_image,
    _migrate_account_icon,
    _migrate_accounts,
    connect,
)

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
        acct_cols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
        assert {"color", "icon_image"} <= acct_cols

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


def test_default_account_fields(tmp_path):
    db_path = os.path.join(tmp_path, "old.db")
    _make_old_db(db_path)
    conn = connect(db_path)
    try:
        a = conn.execute(
            "SELECT name, type, currency, sort, icon, color, icon_image FROM accounts"
        ).fetchone()
        # the default account and the icon/color columns' DEFAULT clauses
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


def test_column_migrations_are_idempotent_when_reapplied(tmp_path):
    # Re-running a column migration must be a no-op: the `_has_column` guards
    # protect the ALTERs. A guard that checks the wrong table/column would try to
    # add an existing column and raise "duplicate column name".
    db_path = os.path.join(tmp_path, "fresh.db")
    conn = connect(db_path)
    try:
        _migrate_account_icon(conn)
        _migrate_account_color_image(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
        assert {"icon", "color", "icon_image"} <= cols
    finally:
        conn.close()


def test_reapplying_accounts_migration_keeps_single_default(tmp_path):
    # Re-running the accounts migration must not insert a second T-Bank nor
    # rebuild away the account_id column.
    db_path = os.path.join(tmp_path, "old.db")
    _make_old_db(db_path)
    conn = connect(db_path)
    try:
        _migrate_accounts(conn)
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(transactions)")}
        assert "account_id" in cols
    finally:
        conn.close()


def test_run_migrations_marks_version_and_skips_when_current(tmp_path):
    db_path = os.path.join(tmp_path, "old.db")
    _make_old_db(db_path)
    conn = connect(db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        # a second connect on the same file is a no-op and leaves the version pinned
        conn.close()
        conn = connect(db_path)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    finally:
        conn.close()
