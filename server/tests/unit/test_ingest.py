import pathlib
import sqlite3
import sys
from pathlib import Path
from typing import cast

from tests.conftest import _Snapshot

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import app.db as dbmod
from app.connectors.base import SyncRow
from app.deps import snapshot
from app.importer import CategoryRule
from app.ingest import categorize_rows, commit_rows, existing_hash_counts, load_rules


def _db(tmp_path: Path) -> sqlite3.Connection:
    c = dbmod.connect(str(tmp_path / "t.db"))
    c.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('u@e.co', 'u@e.co', 'h', 't')"
    )
    uid = c.execute("SELECT id FROM users").fetchone()[0]
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'T-Bank', 'card', 'RUB', 1)",
        (uid,),
    )
    c.commit()
    return c


def _uid(c: sqlite3.Connection) -> int:
    return cast("int", c.execute("SELECT id FROM users").fetchone()[0])


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
    inc = cast("int", c.execute("SELECT id FROM category_groups WHERE name='Inc'").fetchone()[0])
    exp = cast("int", c.execute("SELECT id FROM category_groups WHERE name='Exp'").fetchone()[0])
    cat_sql = "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, ?, ?, ?)"
    c.execute(cat_sql, (inc, "Salary", "salary|wage", 1))
    c.execute(cat_sql, (exp, "Food", "lenta|okey", 2))
    # a category with no keywords must be skipped by build_rules
    c.execute(cat_sql, (exp, "Misc", "", 3))
    c.commit()


def test_load_rules_splits_income_expense(tmp_path: Path) -> None:
    c = _db(tmp_path)
    _seed_categories(c)
    rules = load_rules(c)
    assert [r["name"] for r in rules["IN"]] == ["Salary"]
    assert rules["IN"][0]["keywords"] == ["salary", "wage"]
    assert [r["name"] for r in rules["OUT"]] == ["Food"]  # Misc (no keywords) dropped


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
    bank_category: str = "",
    mcc: str = "",
    category_id: int | None = None,
) -> SyncRow:
    return SyncRow(date, amount, desc, bank_category, mcc, "", category_id=category_id)


def test_existing_hash_counts_is_account_scoped(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct1 = cast("int", c.execute("SELECT MIN(id) FROM accounts").fetchone()[0])
    acct2 = cast("int", c.execute("INSERT INTO accounts (name) VALUES ('Second')").lastrowid)
    commit_rows(c, acct1, [_row("2026-01-01T00:00:00", -100, "A")], source="import")
    c.commit()
    assert len(existing_hash_counts(c, acct1)) == 1
    assert existing_hash_counts(c, acct2) == {}


def test_commit_rows_inserts_with_fields_and_defaults(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct = cast("int", c.execute("SELECT MIN(id) FROM accounts").fetchone()[0])
    bid = c.execute(
        "INSERT INTO import_batches (account_id, source, created_at) VALUES (?, 'sync', 't')",
        (acct,),
    ).lastrowid
    rows = [
        _row("2026-01-01T00:00:00", -100, "A", bank_category="Cafe", mcc="5814", category_id=None),
        _row("2026-01-02T00:00:00", -200, "B"),
    ]
    inserted, skipped = commit_rows(c, acct, rows, source="sync", batch_id=bid)
    c.commit()
    assert (inserted, skipped) == (2, 0)
    got = c.execute(
        "SELECT amount, description, bank_category, mcc, source, batch_id, account_id"
        " FROM transactions ORDER BY id"
    ).fetchall()
    assert got[0]["bank_category"] == "Cafe"
    assert got[0]["mcc"] == "5814"
    assert got[0]["source"] == "sync"
    assert got[0]["batch_id"] == bid
    assert got[0]["account_id"] == acct
    # optional fields default to empty
    assert got[1]["bank_category"] == ""
    assert got[1]["mcc"] == ""


def test_commit_rows_skips_existing_hashes(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct = cast("int", c.execute("SELECT MIN(id) FROM accounts").fetchone()[0])
    rows = [_row("2026-01-01T00:00:00", -100, "A")]
    assert commit_rows(c, acct, rows, source="import") == (1, 0)
    c.commit()
    # same row again -> skipped, nothing inserted
    assert commit_rows(c, acct, rows, source="import") == (0, 1)
    c.commit()
    assert c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1


def test_commit_rows_dedup_is_per_account(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct1 = cast("int", c.execute("SELECT MIN(id) FROM accounts").fetchone()[0])
    acct2 = cast("int", c.execute("INSERT INTO accounts (name) VALUES ('Second')").lastrowid)
    rows = [_row("2026-01-01T00:00:00", -100, "A")]
    commit_rows(c, acct1, rows, source="import")
    c.commit()
    # identical row on a different account is NOT a duplicate
    assert commit_rows(c, acct2, rows, source="import") == (1, 0)


def test_commit_rows_dedup_within_batch(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct = cast("int", c.execute("SELECT MIN(id) FROM accounts").fetchone()[0])
    # three identical rows on a fresh account are all genuinely new
    rows = [_row("2026-01-01T00:00:00", -100, "A")] * 3
    assert commit_rows(c, acct, rows, source="import") == (3, 0)


def test_commit_rows_partial_skip_against_existing(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct = cast("int", c.execute("SELECT MIN(id) FROM accounts").fetchone()[0])
    row = _row("2026-01-01T00:00:00", -100, "A")
    commit_rows(c, acct, [row], source="import")  # DB now holds 1 copy
    c.commit()
    # submitting three copies skips the one already stored, inserts the other two
    assert commit_rows(c, acct, [row, row, row], source="import") == (2, 1)


def test_snapshot_full_shape(tmp_path: Path) -> None:
    c = _db(tmp_path)
    acct = cast("int", c.execute("SELECT MIN(id) FROM accounts").fetchone()[0])
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, type_id)"
        " VALUES (?, 'Bills', 1, (SELECT id FROM category_group_types WHERE type='expense'))",
        (_uid(c),),
    )
    gid = cast("int", c.execute("SELECT id FROM category_groups").fetchone()[0])
    c.execute(
        "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, 'Rent', 'rent', 1)",
        (gid,),
    )
    cid = cast("int", c.execute("SELECT id FROM categories").fetchone()[0])
    c.execute(
        "INSERT INTO transactions (date, amount, description, account_id, hash, source)"
        " VALUES ('2026-01-01T00:00:00', -100, 'x', ?, 'h', 'import')",
        (acct,),
    )
    c.execute(
        "INSERT INTO budgets (category_id, year, month, amount) VALUES (?, 2026, 1, 5000)", (cid,)
    )
    c.commit()
    snap = cast("_Snapshot", snapshot(c, _uid(c)))
    assert [a["name"] for a in snap["accounts"]] == ["T-Bank"]
    assert [g["name"] for g in snap["groups"]] == ["Bills"]
    assert snap["categories"][0]["name"] == "Rent"
    assert snap["categories"][0]["groupId"] == gid
    assert len(snap["transactions"]) == 1
    assert snap["transactions"][0]["accountId"] == acct
    assert snap["transactions"][0]["amount"] == -100
    assert snap["budgets"][0] == {"categoryId": cid, "year": 2026, "month": 1, "amount": 5000}


def test_snapshot_includes_connections_without_secrets(tmp_path: Path) -> None:
    c = _db(tmp_path)
    c.execute(
        "INSERT INTO bank_connections (user_id, bank, kind, status, credentials_encrypted,"
        " created_at, updated_at) VALUES (?, 'tbank', 'playwright', 'connected', ?, 't1', 't2')",
        (_uid(c), b"cipher"),
    )
    c.commit()
    conns = cast("list[dict[str, object]]", cast("_Snapshot", snapshot(c, _uid(c)))["connections"])
    assert len(conns) == 1
    assert conns[0]["bank"] == "tbank"
    assert conns[0]["status"] == "connected"
    assert conns[0]["hasCredentials"] is True
    assert "credentials_encrypted" not in conns[0]


def test_historical_day_counts_span_accounts_and_skip_manual(tmp_path: Path) -> None:
    c = _db(tmp_path)
    uid = _uid(c)
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'Second', 'card', 'RUB', 2)",
        (uid,),
    )
    first, second = [cast("int", r[0]) for r in c.execute("SELECT id FROM accounts ORDER BY id")]
    tx_sql = (
        "INSERT INTO transactions (date, amount, description, account_id, hash, source)"
        " VALUES (?, ?, ?, ?, ?, ?)"
    )
    c.execute(tx_sql, ("2026-07-19T14:22:00", -368000, "Kafe Lesnoj", first, "h1", "sync"))
    c.execute(tx_sql, ("2026-07-19T09:05:00", -368000, "Kafe Lesnoj", second, "h2", "sync"))
    c.execute(tx_sql, ("2026-07-19T10:00:00", -32000, "нетмонет", first, "h3", "manual"))
    c.execute(tx_sql, ("2026-07-18T10:00:00", -50000, "Пятёрочка", first, "h4", "sheets"))
    c.commit()

    from app.ingest import historical_day_counts

    counts = historical_day_counts(c, uid)
    # "sheets" is the retired template importer's label, still in old ledgers
    assert counts == {
        ("2026-07-19", -368000, "kafe lesnoj"): 2,
        ("2026-07-18", -50000, "пятёрочка"): 1,
    }


def test_drop_already_present_is_count_aware() -> None:
    from app.ingest import drop_already_present

    rows = [
        _row("2026-07-19T12:00:00", -368000, "Kafe Lesnoj"),
        _row("2026-07-19T18:00:00", -368000, "Kafe Lesnoj"),
        _row("2026-07-19T18:00:00", -100, "New"),
    ]
    kept, dropped = drop_already_present(rows, {("2026-07-19", -368000, "kafe lesnoj"): 1})
    # one copy is already in the ledger; the second in the batch is genuinely a
    # second operation and stays
    assert dropped == 1
    assert [row.description for row in kept] == ["Kafe Lesnoj", "New"]


def test_dedup_survives_the_bank_rewording_its_own_description(tmp_path: Path) -> None:
    """
    The exact prod duplicate: one pull delivered "…организациях. YandexBank…",
    the next pull the same operation without the dot. One character of drift
    must not read as a new operation — even when the original leg has since
    been merged into a transfer (its source stays 'sync').
    """
    c = _db(tmp_path)
    uid = _uid(c)
    posted = "Операция в других кредитных организациях. YandexBank_C2A g. Moskva RUS"
    reworded = "Операция в других кредитных организациях YandexBank_C2A g. Moskva RUS"
    c.execute(
        "INSERT INTO transactions"
        " (date, amount, description, account_id, hash, source, transfer_id)"
        " VALUES ('2026-07-24T12:38:48', -284300, ?, 1, 'h1', 'sync', 'tr1')",
        (posted,),
    )
    c.commit()

    from app.ingest import drop_already_present, historical_day_counts

    rows = [
        _row("2026-07-24T12:38:48", -284300, reworded),
        _row("2026-07-24T12:13:27", -136300, "Додо Пицца"),
    ]
    kept, dropped = drop_already_present(rows, historical_day_counts(c, uid))
    assert dropped == 1
    assert [row.description for row in kept] == ["Додо Пицца"]
