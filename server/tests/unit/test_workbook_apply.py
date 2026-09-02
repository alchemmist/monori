import pathlib
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import monori.server.app.db as dbmod
from monori.server.app.workbook.apply import apply_workbook as _apply_workbook
from monori.server.app.workbook.apply import budget_conflicts as _budget_conflicts
from monori.server.app.workbook.models import (
    ParsedWorkbook,
    WorkbookApplyResult,
    WorkbookBudget,
    WorkbookCategory,
    WorkbookGroup,
    WorkbookTransaction,
)


def _db(tmp_path: Path) -> tuple[sqlite3.Connection, int, int]:
    c = dbmod.connect(str(tmp_path / "t.db"))
    c.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('u@e.co', 'u@e.co', 'h', 't')",
    )
    user_row = c.execute("SELECT id FROM users").fetchone()
    assert user_row is not None
    uid = user_row[0]
    assert isinstance(uid, int)
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'Card', 'card', 'RUB', 1)",
        (uid,),
    )
    c.commit()
    account_row = c.execute("SELECT id FROM accounts").fetchone()
    assert account_row is not None
    account_id = account_row[0]
    assert isinstance(account_id, int)
    return c, uid, account_id


def _parsed(
    *,
    groups: list[WorkbookGroup] | None = None,
    categories: list[WorkbookCategory] | None = None,
    transactions: list[WorkbookTransaction] | None = None,
    budgets: list[WorkbookBudget] | None = None,
) -> ParsedWorkbook:
    return ParsedWorkbook(
        groups=groups
        if groups is not None
        else [
            WorkbookGroup(name="Daily", sort=1, kind="expense"),
            WorkbookGroup(name="Inflow", sort=5, kind="income"),
        ],
        categories=categories
        if categories is not None
        else [
            WorkbookCategory("Daily", "Groceries", "expense", keywords="lenta"),
            WorkbookCategory("Daily", "Cafes", "expense"),
            WorkbookCategory("Inflow", "Salary", "income"),
        ],
        transactions=transactions
        if transactions is not None
        else [
            WorkbookTransaction(
                "2026-01-05T10:00:00",
                -12550,
                "Lenta",
                "RUB",
                "Super",
                "5411",
                monori_category="Groceries",
            ),
            WorkbookTransaction("2026-01-06T11:00:00", -700, "lenta market", "RUB"),
        ],
        budgets=budgets
        if budgets is not None
        else [
            WorkbookBudget("Groceries", 2026, 1, 20000),
            WorkbookBudget("Ghost", 2026, 1, 999),
        ],
        warnings=[],
        errors=[],
    )


def apply_workbook(
    c: sqlite3.Connection,
    uid: int,
    parsed: ParsedWorkbook,
    mapping: dict[str, int],
    budget_policy: str = "overwrite",
) -> WorkbookApplyResult:
    return _apply_workbook(c, uid, parsed, mapping, budget_policy)


def budget_conflicts(c: sqlite3.Connection, uid: int, budgets: list[WorkbookBudget]) -> int:
    return _budget_conflicts(c, uid, budgets)


def test_apply_creates_groups_categories_transactions_budgets(tmp_path: Path) -> None:
    c, uid, acct = _db(tmp_path)
    result = apply_workbook(c, uid, _parsed(), {"RUB:": acct})
    c.commit()
    assert result.groups_created == 2
    assert result.categories_created == 3
    assert result.inserted == 2
    assert result.skipped == 0
    assert result.budgets_written == 1
    assert result.budgets_skipped == 1
    groups = {
        r["name"]: (r["sort"], r["kind"])
        for r in c.execute(
            "SELECT g.name, g.sort, t.type AS kind FROM category_groups g"
            " JOIN category_group_types t ON t.id=g.type_id",
        )
    }
    assert groups == {"Daily": (1, "expense"), "Inflow": (5, "income")}
    cats = {
        r["name"]: (r["keywords"], r["sort"])
        for r in c.execute("SELECT name, keywords, sort FROM categories")
    }
    assert cats["Groceries"] == ("lenta", 0)
    assert cats["Cafes"] == ("", 1)
    assert cats["Salary"] == ("", 0)


def test_apply_preserves_blank_categories_despite_keywords(tmp_path: Path) -> None:
    c, uid, acct = _db(tmp_path)
    result = apply_workbook(c, uid, _parsed(), {"RUB:": acct})
    c.commit()

    assert result.warnings == [
        "1 rows carry no category in the sheet and were imported uncategorized"
        " — typically transfers between your own accounts, which the spreadsheet"
        " leaves out of the budget as well",
    ]
    rows = list(
        c.execute(
            "SELECT t.description, cat.name FROM transactions t"
            " LEFT JOIN categories cat ON cat.id = t.category_id ORDER BY t.date",
        ),
    )
    assert [(r[0], r[1]) for r in rows] == [
        ("Lenta", "Groceries"),
        ("lenta market", None),
    ]


def test_duplicate_category_names_use_group_identity(tmp_path: Path) -> None:
    c, uid, acct = _db(tmp_path)
    parsed = _parsed(
        groups=[
            WorkbookGroup("Home", 1, "expense"),
            WorkbookGroup("Travel", 2, "expense"),
        ],
        categories=[
            WorkbookCategory("Home", "Other", "expense"),
            WorkbookCategory("Travel", "Other", "expense"),
        ],
        transactions=[
            WorkbookTransaction(
                "2026-01-01T00:00:00",
                -100,
                "home",
                "RUB",
                monori_category="Other",
                monori_category_group="Home",
            ),
            WorkbookTransaction(
                "2026-01-02T00:00:00",
                -200,
                "travel",
                "RUB",
                monori_category="Other",
                monori_category_group="Travel",
            ),
        ],
        budgets=[
            WorkbookBudget("Other", 2026, 1, 1000, group="Home"),
            WorkbookBudget("Other", 2026, 1, 2000, group="Travel"),
        ],
    )

    result = apply_workbook(c, uid, parsed, {"RUB:": acct})
    c.commit()

    assert result.inserted == 2
    rows = c.execute(
        "SELECT t.description, g.name, c.name FROM transactions t"
        " JOIN categories c ON c.id=t.category_id"
        " JOIN category_groups g ON g.id=c.group_id ORDER BY t.date"
    ).fetchall()
    assert [(row[0], row[1], row[2]) for row in rows] == [
        ("home", "Home", "Other"),
        ("travel", "Travel", "Other"),
    ]
    budgets = c.execute(
        "SELECT g.name, b.amount FROM budgets b JOIN categories c ON c.id=b.category_id"
        " JOIN category_groups g ON g.id=c.group_id ORDER BY g.name"
    ).fetchall()
    assert [(row[0], row[1]) for row in budgets] == [("Home", 1000), ("Travel", 2000)]


def test_named_category_outside_the_sheet_beats_keywords(tmp_path: Path) -> None:
    c, uid, acct = _db(tmp_path)
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, type_id)"
        " VALUES (?, 'Mine', 9, (SELECT id FROM category_group_types WHERE type='expense'))",
        (uid,),
    )
    gid = c.execute("SELECT id FROM category_groups WHERE name='Mine'").fetchone()[0]
    c.execute(
        "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, 'Pets', '', 0)",
        (gid,),
    )
    c.commit()
    parsed = _parsed()

    parsed.transactions[1] = replace(parsed.transactions[1], monori_category=" PETS ")
    result = apply_workbook(c, uid, parsed, {"RUB:": acct})
    c.commit()
    assert result.warnings == []
    named = c.execute(
        "SELECT cat.name FROM transactions t JOIN categories cat ON cat.id = t.category_id"
        " WHERE t.description='lenta market'",
    ).fetchone()[0]
    assert named == "Pets"


def test_unknown_named_category_is_left_uncategorized_not_guessed(tmp_path: Path) -> None:
    c, uid, acct = _db(tmp_path)
    parsed = _parsed()
    parsed.transactions[1] = replace(parsed.transactions[1], monori_category="Nowhere")
    result = apply_workbook(c, uid, parsed, {"RUB:": acct})
    c.commit()
    assert (
        c.execute(
            "SELECT category_id FROM transactions WHERE description='lenta market'",
        ).fetchone()[0]
        is None
    )
    assert "Nowhere" in result.warnings[0]


def test_apply_reuses_existing_by_name_and_keeps_keywords(tmp_path: Path) -> None:
    c, uid, acct = _db(tmp_path)
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, type_id)"
        " VALUES (?, 'Daily', 9, (SELECT id FROM category_group_types WHERE type='expense'))",
        (uid,),
    )
    gid = c.execute("SELECT id FROM category_groups").fetchone()[0]
    c.execute(
        "INSERT INTO categories (group_id, name, keywords, sort)"
        " VALUES (?, 'Groceries', 'mine', 4)",
        (gid,),
    )
    c.commit()
    result = apply_workbook(c, uid, _parsed(), {"RUB:": acct})
    c.commit()
    assert result.groups_created == 1
    assert result.categories_created == 2
    row = c.execute("SELECT keywords, sort FROM categories WHERE name='Groceries'").fetchone()
    assert (row[0], row[1]) == ("mine", 4)
    cafes = c.execute("SELECT sort FROM categories WHERE name='Cafes'").fetchone()[0]
    assert cafes == 5


def test_apply_budget_policies(tmp_path: Path) -> None:
    c, uid, acct = _db(tmp_path)
    apply_workbook(c, uid, _parsed(), {"RUB:": acct})
    c.commit()
    cid = c.execute("SELECT id FROM categories WHERE name='Groceries'").fetchone()[0]
    c.execute("UPDATE budgets SET amount=777 WHERE category_id=?", (cid,))
    c.commit()
    result = apply_workbook(c, uid, _parsed(), {"RUB:": acct}, budget_policy="skip")
    c.commit()
    assert result.budgets_written == 0
    assert result.budgets_skipped == 2
    assert c.execute("SELECT amount FROM budgets WHERE category_id=?", (cid,)).fetchone()[0] == 777
    result = apply_workbook(c, uid, _parsed(), {"RUB:": acct}, budget_policy="overwrite")
    c.commit()
    assert result.budgets_written == 1
    assert (
        c.execute("SELECT amount FROM budgets WHERE category_id=?", (cid,)).fetchone()[0] == 20000
    )


def test_apply_batches_per_account_with_source(tmp_path: Path) -> None:
    c, uid, acct = _db(tmp_path)
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'Second', 'card', 'RUB', 2)",
        (uid,),
    )
    c.commit()
    second = c.execute("SELECT id FROM accounts WHERE name='Second'").fetchone()[0]
    parsed = _parsed()
    parsed.transactions[1] = replace(parsed.transactions[1], marker="*2")
    result = apply_workbook(c, uid, parsed, {"RUB:": acct, "RUB:*2": second})
    c.commit()
    assert len(result.batches) == 2
    assert {b.account_id for b in result.batches} == {acct, second}
    assert all(b.inserted == 1 for b in result.batches)
    sources = {r[0] for r in c.execute("SELECT source FROM import_batches")}
    assert sources == {"workbook"}
    tx_sources = {r[0] for r in c.execute("SELECT source FROM transactions")}
    assert tx_sources == {"workbook"}


def test_apply_is_idempotent_on_rerun(tmp_path: Path) -> None:
    c, uid, acct = _db(tmp_path)
    apply_workbook(c, uid, _parsed(), {"RUB:": acct})
    c.commit()
    result = apply_workbook(c, uid, _parsed(), {"RUB:": acct})
    c.commit()
    assert result.inserted == 0
    assert result.skipped == 2
    assert result.groups_created == 0
    assert result.categories_created == 0
    assert c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2


def test_budget_conflicts_counts_only_matching_cells(tmp_path: Path) -> None:
    c, uid, acct = _db(tmp_path)
    cells = _parsed().budgets
    assert budget_conflicts(c, uid, cells) == 0

    apply_workbook(c, uid, _parsed(), {"RUB:": acct})
    c.commit()

    assert budget_conflicts(c, uid, cells) == 1
    assert budget_conflicts(c, uid, []) == 0

    other = [
        WorkbookBudget("Groceries", 2026, 2, 1),
        WorkbookBudget("Groceries", 2027, 1, 1),
        WorkbookBudget("Cafes", 2026, 1, 1),
    ]
    assert budget_conflicts(c, uid, other) == 0


def _row(
    date: str,
    amount: int,
    description: str,
    category: str,
    marker: str = "",
) -> WorkbookTransaction:
    return WorkbookTransaction(
        date=date,
        amount=amount,
        description=description,
        currency="RUB",
        bank_category="Super",
        mcc="5411",
        comment="",
        monori_category=category,
        marker=marker,
    )


def test_every_row_lands_in_its_account_batch_with_the_bank_columns_intact(
    tmp_path: Path,
) -> None:
    """
    The batch is what an import is later browsed and undone by, so each row has.

    to carry the id of the batch on its own account — and the bank's own.
    category and MCC have to survive the trip, since nothing else records them.
    """
    c, uid, acct = _db(tmp_path)
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'Second', 'card', 'RUB', 2)",
        (uid,),
    )
    second = c.execute("SELECT id FROM accounts WHERE name='Second'").fetchone()[0]
    parsed = _parsed(
        transactions=[
            _row("2026-01-05T10:00:00", -12550, "Lenta", "Groceries"),
            _row("2026-01-06T11:00:00", -700, "unfiled one", ""),
            _row("2026-01-07T11:00:00", -800, "unfiled two", ""),
            _row("2026-02-05T10:00:00", -3000, "Pyaterochka", "Groceries", marker="*2947"),
        ],
    )
    result = apply_workbook(c, uid, parsed, {"RUB:": acct, "RUB:*2947": second})
    c.commit()

    assert result.inserted == 4
    assert result.skipped == 0
    assert [b.account_id for b in result.batches] == sorted([acct, second])
    assert [b.inserted for b in result.batches] == [3, 1]
    assert result.warnings[0].startswith("2 rows carry no category in the sheet")

    stamped = {
        r[0]: (r[1], r[2], r[3])
        for r in c.execute("SELECT description, batch_id, bank_category, mcc FROM transactions")
    }
    by_account = {b.account_id: b.batch_id for b in result.batches}
    assert stamped["Lenta"] == (by_account[acct], "Super", "5411")
    assert stamped["Pyaterochka"] == (by_account[second], "Super", "5411")
    assert len(set(by_account.values())) == 2


def test_unmatched_category_names_are_listed_ten_at_a_time(tmp_path: Path) -> None:
    """
    The warning names what was left uncategorized so it can be fixed by hand;.

    a long list is cut off rather than filling the screen.
    """
    c, uid, acct = _db(tmp_path)
    names = [f"Nowhere {i:02d}" for i in range(11)]
    parsed = _parsed(
        transactions=[
            _row(f"2026-01-{i + 1:02d}T10:00:00", -100 * (i + 1), f"row {i}", name)
            for i, name in enumerate(names)
        ],
    )
    result = apply_workbook(c, uid, parsed, {"RUB:": acct})
    c.commit()
    assert result.warnings == [
        "11 category names in the sheet match nothing in monori"
        " — those rows were left uncategorized rather than guessed:"
        f" {', '.join(names[:10])}",
    ]


def test_category_names_match_across_any_spacing(tmp_path: Path) -> None:
    """
    A name typed with a stray double space is the same envelope to a human, so.

    the whole-account fallback compares names with their inner runs of.
    whitespace collapsed, not just their ends trimmed.
    """
    c, uid, acct = _db(tmp_path)
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, type_id)"
        " VALUES (?, 'Mine', 9, (SELECT id FROM category_group_types WHERE type='expense'))",
        (uid,),
    )
    gid = c.execute("SELECT id FROM category_groups WHERE name='Mine'").fetchone()[0]
    c.execute(
        "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, ?, '', 0)",
        (gid, "Lunch  Coffee"),
    )
    c.commit()
    parsed = _parsed(transactions=[_row("2026-01-05T10:00:00", -500, "Kofein", "  Lunch Coffee ")])
    result = apply_workbook(c, uid, parsed, {"RUB:": acct})
    c.commit()
    assert result.warnings == []
    matched = c.execute(
        "SELECT cat.name FROM transactions t JOIN categories cat ON cat.id = t.category_id",
    ).fetchone()[0]
    assert matched == "Lunch  Coffee"


def test_a_category_whose_group_is_missing_does_not_stop_the_rest(tmp_path: Path) -> None:
    """
    Structure and grid can disagree — a category can name a group no sheet ever.

    declared. That one has nowhere to go, but the categories after it in the.
    list still do.
    """
    c, uid, acct = _db(tmp_path)
    parsed = _parsed(
        categories=[
            WorkbookCategory("Nowhere", "Orphan", "expense"),
            WorkbookCategory("Daily", "Groceries", "expense"),
        ],
        groups=[WorkbookGroup("Daily", 1, "expense")],
        transactions=[_row("2026-01-05T10:00:00", -500, "Lenta", "Groceries")],
        budgets=[],
    )
    result = apply_workbook(c, uid, parsed, {"RUB:": acct})
    c.commit()
    assert result.categories_created == 1
    assert result.warnings == []
    names = [r[0] for r in c.execute("SELECT name FROM categories")]
    assert names == ["Groceries"]


def test_apply_skips_rows_a_sync_already_delivered_to_another_account(tmp_path: Path) -> None:
    """
    A sheet kept alongside a live bank sync describes operations the sync.

    already imported — and the sheet's card marker can map them to a different.
    account than the sync routed them to, where the per-account hash is blind.
    Those rows must not be imported a second time.
    """
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
    result = apply_workbook(c, uid, _parsed(), {"RUB:": acct})
    c.commit()
    assert result.inserted == 1
    assert result.skipped == 1
    assert result.warnings[0].startswith("1 rows are already in monori")
    rows = c.execute(
        "SELECT account_id, COUNT(*) FROM transactions WHERE description='Lenta' GROUP BY 1",
    ).fetchall()
    assert [tuple(r) for r in rows] == [(other, 1)]


def test_apply_keeps_a_manual_twin_out_of_the_dedup(tmp_path: Path) -> None:

    c, uid, acct = _db(tmp_path)
    c.execute(
        "INSERT INTO transactions (date, amount, description, account_id, hash, source)"
        " VALUES ('2026-01-05T14:22:00', -12550, 'Lenta', ?, 'h-man', 'manual')",
        (acct,),
    )
    c.commit()
    result = apply_workbook(c, uid, _parsed(), {"RUB:": acct})
    c.commit()
    assert result.inserted == 2
    assert result.skipped == 0
