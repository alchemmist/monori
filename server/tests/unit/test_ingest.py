import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import app.db as dbmod
from app.deps import snapshot
from app.ingest import categorize_rows, commit_rows, existing_hash_counts, load_rules


def _db(tmp_path):
    c = dbmod.connect(str(tmp_path / "t.db"))
    c.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('u@e.co', 'h', 't')")
    uid = c.execute("SELECT id FROM users").fetchone()[0]
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'T-Bank', 'card', 'RUB', 1)",
        (uid,),
    )
    c.commit()
    return c


def _uid(c):
    return c.execute("SELECT id FROM users").fetchone()[0]


def _seed_categories(c):
    uid = _uid(c)
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, kind) VALUES (?, 'Inc', 1, 'income')",
        (uid,),
    )
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, kind) VALUES (?, 'Exp', 2, 'expense')",
        (uid,),
    )
    inc = c.execute("SELECT id FROM category_groups WHERE kind='income'").fetchone()[0]
    exp = c.execute("SELECT id FROM category_groups WHERE kind='expense'").fetchone()[0]
    cat_sql = "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, ?, ?, ?)"
    c.execute(cat_sql, (inc, "Salary", "salary|wage", 1))
    c.execute(cat_sql, (exp, "Food", "lenta|okey", 2))
    # a category with no keywords must be skipped by build_rules
    c.execute(cat_sql, (exp, "Misc", "", 3))
    c.commit()


def test_load_rules_splits_income_expense(tmp_path):
    c = _db(tmp_path)
    _seed_categories(c)
    rules = load_rules(c)
    assert [r["name"] for r in rules["IN"]] == ["Salary"]
    assert rules["IN"][0]["keywords"] == ["salary", "wage"]
    assert [r["name"] for r in rules["OUT"]] == ["Food"]  # Misc (no keywords) dropped


def test_categorize_rows_assigns_by_sign_and_keyword():
    rules = {
        "IN": [{"category_id": 5, "name": "Salary", "keywords": ["salary"]}],
        "OUT": [{"category_id": 9, "name": "Food", "keywords": ["lenta"]}],
    }
    rows = [
        {"description": "Salary June", "amount": 100000},
        {"description": "LENTA store", "amount": -5000},
        {"description": "unknown", "amount": -100},
    ]
    categorize_rows(rows, rules)
    assert [r["category_id"] for r in rows] == [5, 9, None]


def _row(date, amount, desc="x", **kw):
    return {"date": date, "amount": amount, "description": desc, **kw}


def test_existing_hash_counts_is_account_scoped(tmp_path):
    c = _db(tmp_path)
    acct1 = c.execute("SELECT MIN(id) FROM accounts").fetchone()[0]
    acct2 = c.execute("INSERT INTO accounts (name) VALUES ('Second')").lastrowid
    commit_rows(c, acct1, [_row("2026-01-01T00:00:00", -100, "A")], source="import")
    c.commit()
    assert len(existing_hash_counts(c, acct1)) == 1
    assert existing_hash_counts(c, acct2) == {}


def test_commit_rows_inserts_with_fields_and_defaults(tmp_path):
    c = _db(tmp_path)
    acct = c.execute("SELECT MIN(id) FROM accounts").fetchone()[0]
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


def test_commit_rows_skips_existing_hashes(tmp_path):
    c = _db(tmp_path)
    acct = c.execute("SELECT MIN(id) FROM accounts").fetchone()[0]
    rows = [_row("2026-01-01T00:00:00", -100, "A")]
    assert commit_rows(c, acct, rows, source="import") == (1, 0)
    c.commit()
    # same row again -> skipped, nothing inserted
    assert commit_rows(c, acct, rows, source="import") == (0, 1)
    c.commit()
    assert c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1


def test_commit_rows_dedup_is_per_account(tmp_path):
    c = _db(tmp_path)
    acct1 = c.execute("SELECT MIN(id) FROM accounts").fetchone()[0]
    acct2 = c.execute("INSERT INTO accounts (name) VALUES ('Second')").lastrowid
    rows = [_row("2026-01-01T00:00:00", -100, "A")]
    commit_rows(c, acct1, rows, source="import")
    c.commit()
    # identical row on a different account is NOT a duplicate
    assert commit_rows(c, acct2, rows, source="import") == (1, 0)


def test_commit_rows_dedup_within_batch(tmp_path):
    c = _db(tmp_path)
    acct = c.execute("SELECT MIN(id) FROM accounts").fetchone()[0]
    # three identical rows on a fresh account are all genuinely new
    rows = [_row("2026-01-01T00:00:00", -100, "A")] * 3
    assert commit_rows(c, acct, rows, source="import") == (3, 0)


def test_commit_rows_partial_skip_against_existing(tmp_path):
    c = _db(tmp_path)
    acct = c.execute("SELECT MIN(id) FROM accounts").fetchone()[0]
    row = _row("2026-01-01T00:00:00", -100, "A")
    commit_rows(c, acct, [row], source="import")  # DB now holds 1 copy
    c.commit()
    # submitting three copies skips the one already stored, inserts the other two
    assert commit_rows(c, acct, [row, row, row], source="import") == (2, 1)


def test_snapshot_full_shape(tmp_path):
    c = _db(tmp_path)
    acct = c.execute("SELECT MIN(id) FROM accounts").fetchone()[0]
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, kind) VALUES (?, 'Bills', 1, 'expense')",
        (_uid(c),),
    )
    gid = c.execute("SELECT id FROM category_groups").fetchone()[0]
    c.execute(
        "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, 'Rent', 'rent', 1)",
        (gid,),
    )
    cid = c.execute("SELECT id FROM categories").fetchone()[0]
    c.execute(
        "INSERT INTO transactions (date, amount, description, account_id, hash, source)"
        " VALUES ('2026-01-01T00:00:00', -100, 'x', ?, 'h', 'import')",
        (acct,),
    )
    c.execute(
        "INSERT INTO budgets (category_id, year, month, amount) VALUES (?, 2026, 1, 5000)", (cid,)
    )
    c.commit()
    snap = snapshot(c, _uid(c))
    assert [a["name"] for a in snap["accounts"]] == ["T-Bank"]
    assert [g["name"] for g in snap["groups"]] == ["Bills"]
    assert snap["categories"][0]["name"] == "Rent"
    assert snap["categories"][0]["groupId"] == gid
    assert len(snap["transactions"]) == 1
    assert snap["transactions"][0]["accountId"] == acct
    assert snap["transactions"][0]["amount"] == -100
    assert snap["budgets"][0] == {"categoryId": cid, "year": 2026, "month": 1, "amount": 5000}


def test_snapshot_includes_connections_without_secrets(tmp_path):
    c = _db(tmp_path)
    acct = c.execute("SELECT MIN(id) FROM accounts").fetchone()[0]
    c.execute(
        "INSERT INTO bank_connections (account_id, bank, kind, status, credentials_encrypted,"
        " created_at, updated_at) VALUES (?, 'tbank', 'playwright', 'connected', ?, 't1', 't2')",
        (acct, b"cipher"),
    )
    c.commit()
    conns = snapshot(c, _uid(c))["connections"]
    assert len(conns) == 1
    assert conns[0]["bank"] == "tbank"
    assert conns[0]["status"] == "connected"
    assert conns[0]["hasCredentials"] is True
    assert "credentials_encrypted" not in conns[0]
