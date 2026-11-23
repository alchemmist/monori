# Copyright (c) 2026
"""
Unit tests that pin snapshot() scoping and width-related behavior.

These exist because the Python mutation gate runs only unit tests
(``-m "not integration"``), and ``deps.snapshot`` previously had no unit
coverage for: the ``tx_limit`` window, the ``transactions_total`` count
path, category goal fields, user serialization of login/default account,
and the transfer scoping clause.
"""

import sqlite3
from pathlib import Path

import monori.server.app.db as dbmod
from monori.server.app.db_records import UserRecord
from monori.server.app.deps import serialize_user, snapshot


def _db(tmp_path: Path) -> sqlite3.Connection:
    c = dbmod.connect(str(tmp_path / "t.db"))
    for email in ("u1@e.co", "u2@e.co"):
        c.execute(
            "INSERT INTO users (email, email_canonical, password_hash, created_at)"
            " VALUES (?, ?, 'h', 't')",
            (email, email),
        )
    c.executemany(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, ?, 'card', 'RUB', 1)",
        [(1, "Card 1"), (2, "Card 2")],
    )
    c.commit()
    return c


def _add_tx(
    c: sqlite3.Connection, account_id: int, date: str, amount: int, tx_id: int | None = None
) -> int:
    if tx_id is None:
        c.execute(
            "INSERT INTO transactions (date, amount, description, account_id, hash, source)"
            " VALUES (?, ?, 'x', ?, ?, 'import')",
            (date, amount, account_id, f"h{date}{amount}"),
        )
        return _int(c.execute("SELECT last_insert_rowid()").fetchone())
    c.execute(
        "INSERT INTO transactions (id, date, amount, description, account_id, hash, source)"
        " VALUES (?, ?, ?, 'x', ?, ?, 'import')",
        (tx_id, date, amount, account_id, f"h{tx_id}"),
    )
    return tx_id


def _int(row: sqlite3.Row | None) -> int:
    assert row is not None
    value = row[0]
    assert isinstance(value, int)
    return value


def test_snapshot_tx_limit_returns_newest_window_and_true_total(tmp_path: Path) -> None:
    c = _db(tmp_path)
    for day in range(1, 5):
        _add_tx(c, 1, f"2026-01-0{day}T00:00:00", -100 + day)
    c.commit()

    snap = snapshot(c, 1, tx_limit=2)
    assert [tx.amount for tx in snap.transactions] == [-97, -96]
    assert snap.transactions_total == 4

    snap_all = snapshot(c, 1, tx_limit=50)
    assert len(snap_all.transactions) == 4
    assert snap_all.transactions_total == 4


def test_snapshot_limit_exact_boundary_reports_total_behind_window(tmp_path: Path) -> None:
    c = _db(tmp_path)
    for day in range(1, 4):
        _add_tx(c, 1, f"2026-01-0{day}T00:00:00", -day)
    c.commit()

    snap = snapshot(c, 1, tx_limit=3)
    assert len(snap.transactions) == 3
    assert snap.transactions_total == 3


def test_snapshot_sees_category_goal_fields(tmp_path: Path) -> None:
    c = _db(tmp_path)
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, type_id)"
        " VALUES (1, 'Goals', 1, (SELECT id FROM category_group_types WHERE type='expense'))",
    )
    gid = _int(c.execute("SELECT MAX(id) FROM category_groups").fetchone())
    c.execute(
        "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, 'Vacation', 'trip', 1)",
        (gid,),
    )
    cid = _int(c.execute("SELECT MAX(id) FROM categories").fetchone())
    c.execute(
        "UPDATE categories SET goal_target=500000, goal_status='active',"
        " goal_target_date='2026-06-01' WHERE id=?",
        (cid,),
    )
    c.commit()

    snap = snapshot(c, 1)
    cat = next(cat for cat in snap.categories if cat.id == cid)
    assert cat.goal_target == 500000
    assert cat.goal_status == "active"
    assert cat.goal_target_date == "2026-06-01"


def test_serialize_user_exposes_login_and_default_account(tmp_path: Path) -> None:
    c = _db(tmp_path)
    c.execute(
        "UPDATE users SET last_login='2026-02-03T04:05:06', default_account_id=1 WHERE id=1",
    )
    c.commit()
    row = c.execute("SELECT * FROM users WHERE id=1").fetchone()
    user = serialize_user(UserRecord.from_row(row))
    assert user.last_login == "2026-02-03T04:05:06"
    assert user.default_account_id == 1


def test_snapshot_transfers_are_scoped_to_the_requesting_user(tmp_path: Path) -> None:
    c = _db(tmp_path)
    for uid in (1, 2):
        out_id = _add_tx(c, uid, f"2026-01-0{uid}T00:00:00", -100)
        in_id = _add_tx(c, uid, f"2026-02-0{uid}T00:00:00", 100)
        c.execute(
            "INSERT INTO transfers (id, user_id, out_tx_id, in_tx_id, origin, note, created_at)"
            " VALUES (?, ?, ?, ?, 'manual', 'n', '2026-03-01T00:00:00')",
            (f"tr-{uid}", uid, out_id, in_id),
        )
    c.commit()

    snap = snapshot(c, 1)
    assert [transfer.id for transfer in snap.transfers] == ["tr-1"]

    snap2 = snapshot(c, 2)
    assert [transfer.id for transfer in snap2.transfers] == ["tr-2"]
