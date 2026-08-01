import pathlib
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from alembic import command

from app.db import LEGACY_REVISIONS, _alembic_config, connect
from app.importer import tx_hash

if TYPE_CHECKING:
    from collections.abc import Callable

HEAD = "0019"
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


def _make_old_db(path: pathlib.Path) -> None:
    old = sqlite3.connect(path)
    old.executescript(OLD_SCHEMA)
    old.execute(
        "INSERT INTO transactions (id, date, amount, description, hash) VALUES "
        "(1, '2026-01-01T00:00:00', -100, 'a', 'h1'),"
        "(2, '2026-01-02T00:00:00', -200, 'b', 'h2')",
    )
    old.commit()
    old.close()


def _row(conn: sqlite3.Connection, sql: str) -> sqlite3.Row:
    row = conn.execute(sql).fetchone()
    assert row is not None
    assert isinstance(row, sqlite3.Row)
    return row


def _int_scalar(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    assert row is not None
    value = row[0]
    assert isinstance(value, int)
    return value


def _str_scalar(conn: sqlite3.Connection, sql: str) -> str:
    row = conn.execute(sql).fetchone()
    assert row is not None
    value = row[0]
    assert isinstance(value, str)
    return value


def _revision(conn: sqlite3.Connection) -> str:
    return _str_scalar(conn, "SELECT version_num FROM alembic_version")


def test_migration_backfills_existing_transactions(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "old.db"
    _make_old_db(db_path)

    conn = connect(db_path)
    try:
        accounts = conn.execute("SELECT id, name FROM accounts").fetchall()
        assert [a["name"] for a in accounts] == ["T-Bank"]
        default_id = accounts[0]["id"]
        assert isinstance(default_id, int)

        rows = conn.execute("SELECT id, account_id, transfer_id FROM transactions").fetchall()
        assert len(rows) == 2
        assert all(r["account_id"] == default_id for r in rows)
        assert all(r["transfer_id"] is None for r in rows)

        cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(transactions)")}
        assert cols["account_id"]["notnull"] == 1

        icon_row = conn.execute("SELECT icon FROM accounts WHERE id=?", (default_id,)).fetchone()
        assert icon_row is not None
        icon = icon_row["icon"]
        assert isinstance(icon, str)
        assert icon == "wallet"
        acct_cols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
        assert {"color", "icon_image"} <= acct_cols

        assert _revision(conn) == HEAD
    finally:
        conn.close()


def test_migration_is_idempotent(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "old.db"
    _make_old_db(db_path)
    connect(db_path).close()
    conn = connect(db_path)
    try:
        assert _int_scalar(conn, "SELECT COUNT(*) FROM accounts") == 1
        assert _int_scalar(conn, "SELECT COUNT(*) FROM transactions") == 2
        assert _revision(conn) == HEAD
    finally:
        conn.close()


def test_fresh_db_is_created_from_schema_sql(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "fresh.db"
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
            "splits",
            "budgets",
            "bank_connections",
            "import_batches",
            "users",
        } <= tables
        assert _int_scalar(conn, "SELECT COUNT(*) FROM accounts") == 0
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(transactions)")}
        assert {"account_id", "transfer_id", "batch_id"} <= cols
        acct_cols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
        assert "user_id" in acct_cols
        assert _revision(conn) == HEAD
    finally:
        conn.close()


@dataclass(frozen=True, order=True)
class SchemaColumn:
    name: str
    type: str
    not_null: int
    default: str | None
    primary_key: bool


@dataclass(frozen=True)
class TableShape:
    columns: list[SchemaColumn]
    indexes: list[str]


def _describe(db_path: pathlib.Path) -> dict[str, TableShape]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = sorted(
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if r["name"] != "alembic_version" and not r["name"].startswith("sqlite_")
        )
        shape: dict[str, TableShape] = {}
        for t in tables:
            cols = sorted(
                SchemaColumn(
                    name=r["name"],
                    type=r["type"].upper(),
                    not_null=r["notnull"],
                    default=r["dflt_value"],
                    primary_key=bool(r["pk"]),
                )
                for r in conn.execute(f"PRAGMA table_info({t})")
            )
            indexes = sorted(
                r["name"]
                for r in conn.execute(f"PRAGMA index_list({t})")
                if not r["name"].startswith("sqlite_")
            )
            shape[t] = TableShape(cols, indexes)
        return shape
    finally:
        conn.close()


def test_schema_sql_matches_migration_chain(tmp_path: pathlib.Path) -> None:
    fresh = tmp_path / "fresh.db"
    connect(fresh).close()

    chained = tmp_path / "chained.db"
    command.upgrade(_alembic_config(chained), "head")

    assert _describe(fresh) == _describe(chained)


def test_migration_0011_backfills_and_enforces_canonical(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "v6.db"
    command.upgrade(_alembic_config(db_path), "0006")
    raw = sqlite3.connect(db_path)
    raw.execute(
        "INSERT INTO users (email, password_hash, created_at)"
        " VALUES ('a.n.ton+shop@gmail.com', 'h', 't')",
    )
    raw.commit()
    raw.close()

    conn = connect(db_path)
    try:
        assert _revision(conn) == HEAD
        canon = _str_scalar(conn, "SELECT email_canonical FROM users")
        assert canon == "anton@gmail.com"

        try:
            conn.execute(
                "INSERT INTO users (email, email_canonical, password_hash, created_at)"
                " VALUES ('anton@gmail.com', 'anton@gmail.com', 'h', 't')",
            )
            msg = "canonical alias collision was accepted"
            raise AssertionError(msg)
        except sqlite3.IntegrityError:
            pass
    finally:
        conn.close()


def test_migration_0011_reports_canonical_collisions(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "v6.db"
    command.upgrade(_alembic_config(db_path), "0006")
    raw = sqlite3.connect(db_path)
    raw.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES"
        " ('anton@gmail.com', 'h', 't'), ('an.ton@gmail.com', 'h', 't')",
    )
    raw.commit()
    raw.close()

    with pytest.raises(Exception, match="merge these first"):
        connect(db_path).close()


def test_blank_email_canonical_is_rejected(tmp_path: pathlib.Path) -> None:
    builders: tuple[tuple[str, Callable[[pathlib.Path], None]], ...] = (
        ("fresh.db", lambda p: connect(p).close()),
        ("chained.db", lambda p: command.upgrade(_alembic_config(p), "head")),
    )
    for name, builder in builders:
        path = tmp_path / name
        builder(path)
        raw = sqlite3.connect(path)
        try:
            try:
                raw.execute(
                    "INSERT INTO users (email, password_hash, created_at)"
                    " VALUES ('u@e.co', 'h', 't')",
                )
                msg = f"{name}: blank email_canonical on insert was accepted"
                raise AssertionError(msg)
            except sqlite3.IntegrityError:
                pass

            raw.execute(
                "INSERT INTO users (email, email_canonical, password_hash, created_at)"
                " VALUES ('v@e.co', 'v@e.co', 'h', 't')",
            )
            try:
                raw.execute("UPDATE users SET email_canonical = '' WHERE email = 'v@e.co'")
                msg = f"{name}: blank email_canonical on update was accepted"
                raise AssertionError(msg)
            except sqlite3.IntegrityError:
                pass
        finally:
            raw.close()


def test_migration_0011_reports_blank_backfill(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "v6.db"
    command.upgrade(_alembic_config(db_path), "0006")
    raw = sqlite3.connect(db_path)
    raw.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('', 'h', 't')")
    raw.commit()
    raw.close()

    with pytest.raises(Exception, match="fix their address first"):
        connect(db_path).close()


def test_migration_0012_rehashes_with_account_scope(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "v11.db"
    command.upgrade(_alembic_config(db_path), "0011")
    raw = sqlite3.connect(db_path)
    raw.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('u@e.co', 'u@e.co', 'h', 't')",
    )
    raw.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort) VALUES"
        " (1, 'A', 'card', 'RUB', 1), (1, 'B', 'card', 'RUB', 2)",
    )

    raw.execute(
        "INSERT INTO transactions (date, amount, description, account_id, hash) VALUES"
        " ('2026-01-01T00:00:00', -100, 'coffee', 1, 'old'),"
        " ('2026-01-01T00:00:00', -100, 'coffee', 2, 'old')",
    )
    raw.commit()
    raw.close()

    conn = connect(db_path)
    try:
        assert _revision(conn) == HEAD
        rows = conn.execute(
            "SELECT account_id, hash FROM transactions ORDER BY account_id",
        ).fetchall()
        hashes: dict[int, str] = {}
        for row in rows:
            account_id = row["account_id"]
            row_hash = row["hash"]
            assert isinstance(account_id, int)
            assert isinstance(row_hash, str)
            hashes[account_id] = row_hash
        assert hashes[1] == tx_hash(1, "2026-01-01T00:00:00", -100, "coffee")
        assert hashes[2] == tx_hash(2, "2026-01-01T00:00:00", -100, "coffee")
        assert hashes[1] != hashes[2]
    finally:
        conn.close()


def test_legacy_intermediate_user_version_is_adopted(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "v1.db"
    command.upgrade(_alembic_config(db_path), "0002")
    raw = sqlite3.connect(db_path)
    raw.execute("DROP TABLE alembic_version")
    raw.execute("PRAGMA user_version = 1")
    raw.commit()
    raw.close()

    conn = connect(db_path)
    try:
        assert _revision(conn) == HEAD
        assert _int_scalar(conn, "SELECT COUNT(*) FROM accounts") == 1
        acct_cols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
        assert {"icon", "color", "icon_image"} <= acct_cols
        tables = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"bank_connections", "import_batches", "users"} <= tables
    finally:
        conn.close()


def test_upgrade_assigns_orphans_to_earliest_user(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "v6.db"
    command.upgrade(_alembic_config(db_path), "0006")
    raw = sqlite3.connect(db_path)
    raw.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('a@b.co', 'h', 't')")
    raw.execute(
        "INSERT INTO accounts (name, type, currency, sort) VALUES ('Old', 'card', 'RUB', 1)",
    )
    raw.execute("INSERT INTO category_groups (name, sort, kind) VALUES ('G', 1, 'expense')")
    raw.commit()
    raw.close()

    conn = connect(db_path)
    try:
        uid = _int_scalar(conn, "SELECT MIN(id) FROM users")
        assert _int_scalar(conn, "SELECT user_id FROM accounts") == uid
        assert _int_scalar(conn, "SELECT user_id FROM category_groups") == uid
    finally:
        conn.close()


def test_concurrent_first_connects_bootstrap_once(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "race.db"
    calls: list[int] = []
    real_stamp = command.stamp

    def counted_bootstrap_call(cfg: object, revision: str) -> None:
        calls.append(1)
        time.sleep(0.05)
        real_stamp(cfg, revision)

    monkeypatch.setattr(command, "stamp", counted_bootstrap_call)
    threads = [threading.Thread(target=lambda: connect(db_path).close()) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1


def test_default_account_fields(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "old.db"
    _make_old_db(db_path)
    conn = connect(db_path)
    try:
        a = _row(
            conn,
            "SELECT name, type, currency, sort, icon, color, icon_image FROM accounts",
        )
        assert a["name"] == "T-Bank"
        assert a["type"] == "card"
        assert a["currency"] == "RUB"
        assert a["sort"] == 1
        assert a["icon"] == "wallet"
        assert a["color"] == "#5b6472"
        assert a["icon_image"] is None
    finally:
        conn.close()


def test_new_account_gets_column_defaults(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "fresh.db"
    conn = connect(db_path)
    try:
        conn.execute("INSERT INTO accounts (name) VALUES ('Extra')")
        a = _row(
            conn,
            "SELECT type, currency, sort, archived, opening_balance, icon, color, icon_image"
            " FROM accounts WHERE name='Extra'",
        )
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


def test_connection_conversion_to_user_level(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "conv.db"
    command.upgrade(_alembic_config(db_path), "0007")
    c = sqlite3.connect(db_path)
    c.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('u@e.co', 'h', 't')")
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (1, 'Card', 'card', 'RUB', 1)",
    )
    acct_id = _int_scalar(c, "SELECT id FROM accounts WHERE name='Card'")
    c.execute(
        "INSERT INTO bank_connections (account_id, bank, kind, status, created_at, updated_at)"  # noqa: S608
        f" VALUES ({acct_id}, 'tbank', 'playwright', 'connected', 't1', 't2')",
    )
    c.commit()
    c.close()

    command.upgrade(_alembic_config(db_path), "head")
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    conn_row = _row(c, "SELECT * FROM bank_connections")
    assert conn_row["user_id"] == 1
    conn_cols = conn_row.keys()
    assert "account_id" not in conn_cols
    acct = _row(c, "SELECT connection_id, bank_ref FROM accounts WHERE name='Card'")
    assert acct["connection_id"] == conn_row["id"]
    assert acct["bank_ref"] == ""
    c.close()
