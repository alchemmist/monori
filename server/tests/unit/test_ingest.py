import pathlib
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import app.db as dbmod
from app.connectors.base import SyncRow
from app.deps import snapshot
from app.domain_types import TransactionSource
from app.importer import CategoryRule
from app.ingest import (
    categorize_rows,
    commit_rows,
    drop_already_present,
    existing_hash_counts,
    historical_day_counts,
    load_rules,
)


def _db(tmp_path: Path) -> sqlite3.Connection:
    c = dbmod.connect(str(tmp_path / "t.db"))
    c.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('u@e.co', 'u@e.co', 'h', 't')",
    )
    uid = _required_int(c.execute("SELECT id FROM users").fetchone())
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'T-Bank', 'card', 'RUB', 1)",
        (uid,),
    )
    c.commit()
    return c


def _uid(c: sqlite3.Connection) -> int:
    return _required_int(c.execute("SELECT id FROM users").fetchone())


def _required_int(row: sqlite3.Row | None) -> int:
    assert row is not None
    value = row[0]
    assert isinstance(value, int)
    return value


def _inserted_id(cursor: sqlite3.Cursor) -> int:
    value = cursor.lastrowid
    assert value is not None
    return value


def _seed_categories(c: sqlite3.Connection) -> None:
    uid = _uid(c)
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, type_id)"
        " VALUES (?, 'Inc', 1, (SELECT id FROM category_group_types WHERE type='income'))",
        (uid,),
    )
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, type_id)"
        " VALUES (?, 'Exp', 2, (SELECT id FROM category_group_types WHERE type='expense'))",
        (uid,),
    )
    inc = _required_int(c.execute("SELECT id FROM category_groups WHERE name='Inc'").fetchone())
    exp = _required_int(c.execute("SELECT id FROM category_groups WHERE name='Exp'").fetchone())
    cat_sql = "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, ?, ?, ?)"
    c.execute(cat_sql, (inc, "Salary", "salary|wage", 1))
    c.execute(cat_sql, (exp, "Food", "lenta|okey", 2))

    c.execute(cat_sql, (exp, "Misc", "", 3))
    c.commit()


def test_load_rules_splits_income_expense(tmp_path: Path) -> None:
    c = _db(tmp_path)
    _seed_categories(c)
    rules = load_rules(c)
    assert [r["name"] for r in rules["IN"]] == ["Salary"]
    assert rules["IN"][0]["keywords"] == ["salary", "wage"]
    assert [r["name"] for r in rules["OUT"]] == ["Food"]


def test_categorize_rows_assigns_by_sign_and_keyword() -> None:
    rules: dict[str, list[CategoryRule]] = {
        "IN": [CategoryRule(category_id=5, name="Salary", keywords=["salary"])],
        "OUT": [CategoryRule(category_id=9, name="Food", keywords=["lenta"])],
    }
    rows = [
        _row("2026-01-01", 100000, "Salary June"),
        _row("2026-01-01", -5000, "LENTA store"),
        _row("2026-01-01", -100, "unknown"),
    ]
    categorize_rows(rows, rules)
    assert [row.category_id for row in rows] == [5, 9, None]


def _row(
    date: str,
    amount: int,
    desc: str = "x",
    *,
    tags: tuple[str, str] = ("", ""),
    category_id: int | None = None,
) -> SyncRow:
    bank_category, mcc = tags
    return SyncRow(date, amount, desc, bank_category, mcc, "", category_id=category_id)


def test_existing_hash_counts_is_account_scoped(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct1 = _required_int(c.execute("SELECT MIN(id) FROM accounts").fetchone())
    acct2 = _inserted_id(c.execute("INSERT INTO accounts (name) VALUES ('Second')"))
    commit_rows(c, acct1, [_row("2026-01-01T00:00:00", -100, "A")], source=TransactionSource.IMPORT)
    c.commit()
    assert len(existing_hash_counts(c, acct1)) == 1
    assert existing_hash_counts(c, acct2) == {}


def test_commit_rows_inserts_with_fields_and_defaults(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct = _required_int(c.execute("SELECT MIN(id) FROM accounts").fetchone())
    bid = c.execute(
        "INSERT INTO import_batches (account_id, source, created_at) VALUES (?, 'sync', 't')",
        (acct,),
    ).lastrowid
    rows = [
        _row(
            "2026-01-01T00:00:00",
            -100,
            "A",
            tags=("Cafe", "5814"),
            category_id=None,
        ),
        _row("2026-01-02T00:00:00", -200, "B"),
    ]
    inserted, skipped = commit_rows(c, acct, rows, source=TransactionSource.SYNC, batch_id=bid)
    c.commit()
    assert (inserted, skipped) == (2, 0)
    got = c.execute(
        "SELECT amount, description, bank_category, mcc, source, batch_id, account_id"
        " FROM transactions ORDER BY id",
    ).fetchall()
    assert got[0]["bank_category"] == "Cafe"
    assert got[0]["mcc"] == "5814"
    assert got[0]["source"] == "sync"
    assert got[0]["batch_id"] == bid
    assert got[0]["account_id"] == acct

    assert got[1]["bank_category"] == ""
    assert got[1]["mcc"] == ""


def test_commit_rows_skips_existing_hashes(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct = _required_int(c.execute("SELECT MIN(id) FROM accounts").fetchone())
    rows = [_row("2026-01-01T00:00:00", -100, "A")]
    assert commit_rows(c, acct, rows, source=TransactionSource.IMPORT) == (1, 0)
    c.commit()

    assert commit_rows(c, acct, rows, source=TransactionSource.IMPORT) == (0, 1)
    c.commit()
    assert c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1


def test_commit_rows_dedup_is_per_account(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct1 = _required_int(c.execute("SELECT MIN(id) FROM accounts").fetchone())
    acct2 = _inserted_id(c.execute("INSERT INTO accounts (name) VALUES ('Second')"))
    rows = [_row("2026-01-01T00:00:00", -100, "A")]
    commit_rows(c, acct1, rows, source=TransactionSource.IMPORT)
    c.commit()

    assert commit_rows(c, acct2, rows, source=TransactionSource.IMPORT) == (1, 0)


def test_commit_rows_dedup_within_batch(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct = _required_int(c.execute("SELECT MIN(id) FROM accounts").fetchone())

    rows = [_row("2026-01-01T00:00:00", -100, "A")] * 3
    assert commit_rows(c, acct, rows, source=TransactionSource.IMPORT) == (3, 0)


def test_commit_rows_partial_skip_against_existing(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct = _required_int(c.execute("SELECT MIN(id) FROM accounts").fetchone())
    row = _row("2026-01-01T00:00:00", -100, "A")
    commit_rows(c, acct, [row], source=TransactionSource.IMPORT)
    c.commit()

    assert commit_rows(c, acct, [row, row, row], source=TransactionSource.IMPORT) == (2, 1)


def test_snapshot_full_shape(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct = _required_int(c.execute("SELECT MIN(id) FROM accounts").fetchone())
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, type_id)"
        " VALUES (?, 'Bills', 1, (SELECT id FROM category_group_types WHERE type='expense'))",
        (_uid(c),),
    )
    gid = _required_int(c.execute("SELECT id FROM category_groups").fetchone())
    c.execute(
        "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, 'Rent', 'rent', 1)",
        (gid,),
    )
    cid = _required_int(c.execute("SELECT id FROM categories").fetchone())
    c.execute(
        "INSERT INTO transactions (date, amount, description, account_id, hash, source)"
        " VALUES ('2026-01-01T00:00:00', -100, 'x', ?, 'h', 'import')",
        (acct,),
    )
    c.execute(
        "INSERT INTO budgets (category_id, year, month, amount) VALUES (?, 2026, 1, 5000)",
        (cid,),
    )
    c.commit()
    snap = snapshot(c, _uid(c))
    assert [a.name for a in snap.accounts] == ["T-Bank"]
    assert [g.name for g in snap.groups] == ["Bills"]
    assert snap.categories[0].name == "Rent"
    assert snap.categories[0].group_id == gid
    assert len(snap.transactions) == 1
    assert snap.transactions[0].account_id == acct
    assert snap.transactions[0].amount == -100
    budget = snap.budgets[0]
    assert (budget.category_id, budget.year, budget.month, budget.amount) == (cid, 2026, 1, 5000)


def test_snapshot_includes_connections_without_secrets(tmp_path: Path) -> None:
    c = _db(tmp_path)
    c.execute(
        "INSERT INTO bank_connections (user_id, bank, kind, status, credentials_encrypted,"
        " created_at, updated_at) VALUES (?, 'tbank', 'playwright', 'connected', ?, 't1', 't2')",
        (_uid(c), b"cipher"),
    )
    c.commit()
    conns = snapshot(c, _uid(c)).connections
    assert len(conns) == 1
    assert conns[0].bank == "tbank"
    assert conns[0].status == "connected"
    assert conns[0].has_credentials is True
    assert not hasattr(conns[0], "credentials_encrypted")


def test_historical_day_counts_span_accounts_and_skip_manual(tmp_path: Path) -> None:
    c = _db(tmp_path)
    uid = _uid(c)
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'Second', 'card', 'RUB', 2)",
        (uid,),
    )
    account_rows = c.execute("SELECT id FROM accounts ORDER BY id").fetchall()
    first, second = [_required_int(row) for row in account_rows]
    tx_sql = (
        "INSERT INTO transactions (date, amount, description, account_id, hash, source)"
        " VALUES (?, ?, ?, ?, ?, ?)"
    )
    c.execute(tx_sql, ("2026-07-19T14:22:00", -368000, "Kafe Lesnoj", first, "h1", "sync"))
    c.execute(tx_sql, ("2026-07-19T09:05:00", -368000, "Kafe Lesnoj", second, "h2", "sync"))
    c.execute(tx_sql, ("2026-07-19T10:00:00", -32000, "No coins", first, "h3", "manual"))
    c.execute(tx_sql, ("2026-07-18T10:00:00", -50000, "Pyaterochka", first, "h4", "sheets"))
    c.commit()

    counts = historical_day_counts(c, uid)

    assert counts == {
        ("2026-07-19", -368000, "kafe lesnoj"): 2,
        ("2026-07-18", -50000, "pyaterochka"): 1,
    }


def test_drop_already_present_is_count_aware() -> None:
    rows = [
        _row("2026-07-19T12:00:00", -368000, "Kafe Lesnoj"),
        _row("2026-07-19T18:00:00", -368000, "Kafe Lesnoj"),
        _row("2026-07-19T18:00:00", -100, "New"),
    ]
    kept, dropped = drop_already_present(rows, {("2026-07-19", -368000, "kafe lesnoj"): 1})

    assert dropped == 1
    assert [row.description for row in kept] == ["Kafe Lesnoj", "New"]


def test_dedup_survives_the_bank_rewording_its_own_description(tmp_path: Path) -> None:
    """
    The exact prod duplicate: one pull delivered "...organizations. YandexBank...".

    the next pull the same operation without the dot. One character of drift.
    must not read as a new operation — even when the original leg has since
    been merged into a transfer (its source stays 'sync').
    """
    c = _db(tmp_path)
    uid = _uid(c)
    posted = "Operation in another bank. YandexBank_C2A g. Moskva RUS"
    reworded = "Operation in another bank YandexBank_C2A g. Moskva RUS"
    c.execute(
        "INSERT INTO transactions"
        " (date, amount, description, account_id, hash, source, transfer_id)"
        " VALUES ('2026-07-24T12:38:48', -284300, ?, 1, 'h1', 'sync', 'tr1')",
        (posted,),
    )
    c.commit()

    rows = [
        _row("2026-07-24T12:38:48", -284300, reworded),
        _row("2026-07-24T12:13:27", -136300, "Dodo Pizza"),
    ]
    kept, dropped = drop_already_present(rows, historical_day_counts(c, uid))
    assert dropped == 1
    assert [row.description for row in kept] == ["Dodo Pizza"]
