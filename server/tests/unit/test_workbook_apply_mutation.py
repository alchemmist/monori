# Copyright (c) 2026
"""
Targets the parts of apply that the existing suite pins only loosely: the.

timestamp format stamped on a batch, the budget counters when more than one.
cell is written, and the exact text of the "already imported" warning.
"""

import pathlib
import re
import sqlite3
import sys
from dataclasses import replace

import pytest

import monori.server.app.db as dbmod
from monori.server.app.workbook.apply import _drop_already_present, apply_workbook
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
        (
            "1 rows are already in monori — delivered by a bank sync or an"
            " earlier import, possibly onto a different account — and were not"
            " imported again"
        ),
    ]


def test_historical_dedup_consumes_only_the_recorded_number_of_each_operation() -> None:
    rows = [
        WorkbookTransaction("2026-01-05T09:00:00", -100, "Coffee!", "RUB"),
        WorkbookTransaction("2026-01-05T09:30:00", -200, "Bus", "RUB"),
        WorkbookTransaction("2026-01-05T10:00:00", -100, " COFFEE ", "RUB"),
        WorkbookTransaction("2026-01-05T11:00:00", -100, "coffee", "RUB"),
        WorkbookTransaction("2026-01-05T11:30:00", -200, "bus", "RUB"),
        WorkbookTransaction("2026-01-06T09:00:00", -100, "coffee", "RUB"),
        WorkbookTransaction("2026-01-05T12:00:00", -300, "coffee", "RUB"),
        WorkbookTransaction("2026-01-05T12:30:00", -100, "Tea", "RUB"),
    ]
    history = {("2026-01-05", -100, "coffee"): 2, ("2026-01-05", -200, "bus"): 1}

    kept, dropped = _drop_already_present(rows, history)

    assert kept == rows[3:]
    assert dropped == 3
    assert history == {("2026-01-05", -100, "coffee"): 2, ("2026-01-05", -200, "bus"): 1}


@pytest.mark.parametrize(
    ("group", "category", "expected_group", "expected_category"),
    [
        (" hOME ", "  WEEKLY\tfood ", "Home", "Weekly Food"),
        ("Travel", "OTHER", "Travel", "Other"),
        ("", "Weekly Food", "Home", "Weekly Food"),
        ("Missing", "Weekly Food", None, None),
        ("", "Other", None, None),
    ],
    ids=[
        "normalized-identity",
        "explicit-duplicate",
        "unique-legacy",
        "unknown-group",
        "ambiguous",
    ],
)
def test_transactions_and_budgets_never_guess_a_category_group(
    tmp_path: pathlib.Path,
    group: str,
    category: str,
    expected_group: str | None,
    expected_category: str | None,
) -> None:
    c, uid, acct = _db(tmp_path)
    parsed = replace(
        _parsed([]),
        groups=[WorkbookGroup("Home", 1, "expense"), WorkbookGroup("Travel", 2, "expense")],
        categories=[
            WorkbookCategory("Home", "Weekly Food", "expense"),
            WorkbookCategory("Home", "Other", "expense"),
            WorkbookCategory("Travel", "Other", "expense"),
        ],
        transactions=[
            WorkbookTransaction(
                "2026-01-05T10:00:00",
                -12550,
                "Shop",
                "RUB",
                monori_category=category,
                monori_category_group=group,
            ),
        ],
        budgets=[WorkbookBudget(category, 2026, 2, 32100, group=group)],
    )

    result = apply_workbook(c, uid, parsed, {"RUB:": acct})
    c.commit()

    assert result.inserted == 1
    transaction = c.execute(
        "SELECT g.name, cat.name FROM transactions t"
        " LEFT JOIN categories cat ON cat.id=t.category_id"
        " LEFT JOIN category_groups g ON g.id=cat.group_id",
    ).fetchone()
    assert tuple(transaction) == (expected_group, expected_category)
    budgets = c.execute(
        "SELECT g.name, cat.name, b.year, b.month, b.amount FROM budgets b"
        " JOIN categories cat ON cat.id=b.category_id"
        " JOIN category_groups g ON g.id=cat.group_id",
    ).fetchall()
    if expected_group is None:
        assert result.budgets_written == 0
        assert result.budgets_skipped == 1
        assert budgets == []
        assert result.warnings == [
            "1 category names in the sheet match nothing in monori"
            " — those rows were left uncategorized rather than guessed: " + category,
        ]
    else:
        assert result.budgets_written == 1
        assert result.budgets_skipped == 0
        assert [tuple(row) for row in budgets] == [
            (expected_group, expected_category, 2026, 2, 32100),
        ]
        assert result.warnings == []


def test_skip_policy_preserves_multiple_conflicts_but_imports_new_months(
    tmp_path: pathlib.Path,
) -> None:
    c, uid, acct = _db(tmp_path)
    apply_workbook(c, uid, _parsed([_b("Groceries"), _b("Cafes")]), {"RUB:": acct})
    c.commit()

    result = apply_workbook(
        c,
        uid,
        _parsed(
            [
                _b("Groceries", amount=20000),
                _b("Cafes", amount=30000),
                _b("Groceries", month=2, amount=40000),
                _b("Cafes", month=2, amount=50000),
            ],
        ),
        {"RUB:": acct},
        budget_policy="skip",
    )
    c.commit()

    assert result.budgets_written == 2
    assert result.budgets_skipped == 2
    budgets = c.execute(
        "SELECT cat.name, b.year, b.month, b.amount FROM budgets b"
        " JOIN categories cat ON cat.id=b.category_id ORDER BY cat.name, b.month",
    ).fetchall()
    assert [tuple(row) for row in budgets] == [
        ("Cafes", 2026, 1, 10000),
        ("Cafes", 2026, 2, 50000),
        ("Groceries", 2026, 1, 10000),
        ("Groceries", 2026, 2, 40000),
    ]
