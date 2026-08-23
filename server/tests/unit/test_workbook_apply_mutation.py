"""
Targets the parts of apply that the existing suite pins only loosely: the.

timestamp format stamped on a batch, the budget counters when more than one.
cell is written, and the exact text of the "already imported" warning.
"""

import pathlib
import re
import sqlite3
import sys

import monori.server.app.db as dbmod
from monori.server.app.workbook.apply import apply_workbook
from monori.server.app.workbook.models import (
    ParsedWorkbook,
    WorkbookBudget,
    WorkbookCategory,
    WorkbookGroup,
    WorkbookTransaction,
)


def _db(tmp_path: pathlib.Path) -> tuple[sqlite3.Connection, int, int]:
    c = dbmod.connect(str(tmp_path / "t.db"))
    c.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('u@e.co', 'u@e.co', 'h', 't')",
    )
    uid = c.execute("SELECT id FROM users").fetchone()[0]
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'Card', 'card', 'RUB', 1)",
        (uid,),
    )
    c.commit()
    return c, uid, c.execute("SELECT id FROM accounts").fetchone()[0]


def _parsed(budgets: list[WorkbookBudget]) -> ParsedWorkbook:
    return ParsedWorkbook(
        groups=[WorkbookGroup(name="Daily", sort=1, kind="expense")],
        categories=[
            WorkbookCategory(group="Daily", name="Groceries", group_kind="expense"),
            WorkbookCategory(group="Daily", name="Cafes", group_kind="expense"),
        ],
        transactions=[
            WorkbookTransaction(
                date="2026-01-05T10:00:00",
                amount=-12550,
                description="Lenta",
                bank_category="Super",
                mcc="5411",
                comment="",
                monori_category="Groceries",
                marker="",
                currency="RUB",
            ),
        ],
        budgets=budgets,
        warnings=[],
        errors=[],
    )


def _b(category: str, month: int = 1, amount: int = 10000) -> WorkbookBudget:
    return WorkbookBudget(category=category, year=2026, month=month, amount=amount)


def test_import_batch_created_at_is_a_full_iso_timestamp(tmp_path: pathlib.Path) -> None:
    c, uid, acct = _db(tmp_path)
    apply_workbook(c, uid, _parsed([]), {"RUB:": acct})
    c.commit()
    stamp = c.execute("SELECT created_at FROM import_batches").fetchone()[0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", stamp)


def test_overwrite_counts_every_written_budget(tmp_path: pathlib.Path) -> None:
    c, uid, acct = _db(tmp_path)
    result = apply_workbook(
        c,
        uid,
        _parsed([_b("Groceries"), _b("Cafes")]),
        {"RUB:": acct},
        budget_policy="overwrite",
    )
    c.commit()
    assert result.budgets_written == 2
    assert result.budgets_skipped == 0


def test_skip_policy_counts_every_freshly_inserted_budget(tmp_path: pathlib.Path) -> None:
    c, uid, acct = _db(tmp_path)
    result = apply_workbook(
        c,
        uid,
        _parsed([_b("Groceries"), _b("Cafes")]),
        {"RUB:": acct},
        budget_policy="skip",
    )
    c.commit()
    assert result.budgets_written == 2
    assert result.budgets_skipped == 0


def test_an_unmatched_budget_does_not_halt_the_rest(tmp_path: pathlib.Path) -> None:
    c, uid, acct = _db(tmp_path)

    result = apply_workbook(c, uid, _parsed([_b("Ghost"), _b("Groceries")]), {"RUB:": acct})
    c.commit()
    assert result.budgets_written == 1
    assert result.budgets_skipped == 1


def test_already_imported_warning_reads_in_full(tmp_path: pathlib.Path) -> None:
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
    assert result.warnings == [
        "1 rows are already in monori — delivered by a bank sync or an"
        " earlier import, possibly onto a different account — and were not"
        " imported again",
    ]
