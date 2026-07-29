"""
Targets the parts of apply that the existing suite pins only loosely: the
timestamp format stamped on a batch, the budget counters when more than one
cell is written, and the exact text of the "already imported" warning.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import app.db as dbmod
from app.workbook.apply import apply_workbook


def _db(tmp_path):
    c = dbmod.connect(str(tmp_path / "t.db"))
    c.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('u@e.co', 'u@e.co', 'h', 't')"
    )
    uid = c.execute("SELECT id FROM users").fetchone()[0]
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'Card', 'card', 'RUB', 1)",
        (uid,),
    )
    c.commit()
    return c, uid, c.execute("SELECT id FROM accounts").fetchone()[0]


def _parsed(budgets):
    return {
        "groups": [{"name": "Daily", "sort": 1, "kind": "expense"}],
        "categories": [
            {"group": "Daily", "name": "Groceries", "keywords": "", "group_kind": "expense"},
            {"group": "Daily", "name": "Cafes", "keywords": "", "group_kind": "expense"},
        ],
        "transactions": [
            {
                "date": "2026-01-05T10:00:00",
                "amount": -12550,
                "description": "Lenta",
                "bank_category": "Super",
                "mcc": "5411",
                "comment": "",
                "monori_category": "Groceries",
                "marker": "",
                "currency": "RUB",
            }
        ],
        "budgets": budgets,
        "warnings": [],
        "errors": [],
    }


def _b(category, month=1, amount=10000):
    return {"category": category, "year": 2026, "month": month, "amount": amount}


def test_import_batch_created_at_is_a_full_iso_timestamp(tmp_path):
    c, uid, acct = _db(tmp_path)
    apply_workbook(c, uid, _parsed([]), {"RUB:": acct})
    c.commit()
    stamp = c.execute("SELECT created_at FROM import_batches").fetchone()[0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", stamp)


def test_overwrite_counts_every_written_budget(tmp_path):
    c, uid, acct = _db(tmp_path)
    result = apply_workbook(
        c, uid, _parsed([_b("Groceries"), _b("Cafes")]), {"RUB:": acct}, budget_policy="overwrite"
    )
    c.commit()
    assert result["budgetsWritten"] == 2
    assert result["budgetsSkipped"] == 0


def test_skip_policy_counts_every_freshly_inserted_budget(tmp_path):
    c, uid, acct = _db(tmp_path)
    result = apply_workbook(
        c, uid, _parsed([_b("Groceries"), _b("Cafes")]), {"RUB:": acct}, budget_policy="skip"
    )
    c.commit()
    assert result["budgetsWritten"] == 2
    assert result["budgetsSkipped"] == 0


def test_an_unmatched_budget_does_not_halt_the_rest(tmp_path):
    c, uid, acct = _db(tmp_path)
    # the unmatched cell comes first: a `break` here would drop the valid one after it
    result = apply_workbook(c, uid, _parsed([_b("Ghost"), _b("Groceries")]), {"RUB:": acct})
    c.commit()
    assert result["budgetsWritten"] == 1
    assert result["budgetsSkipped"] == 1


def test_already_imported_warning_reads_in_full(tmp_path):
    c, uid, acct = _db(tmp_path)
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'Credit', 'card', 'RUB', 2)",
        (uid,),
    )
    other = c.execute("SELECT id FROM accounts WHERE name='Credit'").fetchone()[0]
    c.execute(
        "INSERT INTO transactions (date, amount, description, account_id, hash, source)"
        " VALUES ('2026-01-05T14:22:00', -12550, 'Lenta', ?, 'h-sync', 'sync')",
        (other,),
    )
    c.commit()
    result = apply_workbook(c, uid, _parsed([]), {"RUB:": acct})
    c.commit()
    assert result["warnings"] == [
        "1 rows are already in monori — delivered by a bank sync or an"
        " earlier import, possibly onto a different account — and were not"
        " imported again"
    ]
