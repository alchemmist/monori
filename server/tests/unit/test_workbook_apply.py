import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import app.db as dbmod
from app.workbook.apply import apply_workbook, budget_conflicts


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


def _parsed(**over):
    base = {
        "groups": [
            {"name": "Daily", "sort": 1, "kind": "expense"},
            {"name": "Inflow", "sort": 5, "kind": "income"},
        ],
        "categories": [
            {"group": "Daily", "name": "Groceries", "keywords": "lenta", "group_kind": "expense"},
            {"group": "Daily", "name": "Cafes", "keywords": "", "group_kind": "expense"},
            {"group": "Inflow", "name": "Salary", "keywords": "", "group_kind": "income"},
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
            },
            {
                "date": "2026-01-06T11:00:00",
                "amount": -700,
                "description": "lenta market",
                "bank_category": "",
                "mcc": "",
                "comment": "",
                "monori_category": "",
                "marker": "",
            },
        ],
        "budgets": [
            {"category": "Groceries", "year": 2026, "month": 1, "amount": 20000},
            {"category": "Ghost", "year": 2026, "month": 1, "amount": 999},
        ],
        "warnings": [],
        "errors": [],
    }
    base.update(over)
    return base


def test_apply_creates_groups_categories_transactions_budgets(tmp_path):
    c, uid, acct = _db(tmp_path)
    result = apply_workbook(c, uid, _parsed(), {"": acct})
    c.commit()
    assert result["groupsCreated"] == 2
    assert result["categoriesCreated"] == 3
    assert result["inserted"] == 2
    assert result["skipped"] == 0
    assert result["budgetsWritten"] == 1
    assert result["budgetsSkipped"] == 1
    groups = {
        r["name"]: (r["sort"], r["kind"])
        for r in c.execute("SELECT name, sort, kind FROM category_groups")
    }
    assert groups == {"Daily": (1, "expense"), "Inflow": (5, "income")}
    cats = {
        r["name"]: (r["keywords"], r["sort"])
        for r in c.execute("SELECT name, keywords, sort FROM categories")
    }
    assert cats["Groceries"] == ("lenta", 0)
    assert cats["Cafes"] == ("", 1)
    assert cats["Salary"] == ("", 0)


def test_apply_categorizes_by_explicit_name_then_keywords(tmp_path):
    c, uid, acct = _db(tmp_path)
    apply_workbook(c, uid, _parsed(), {"": acct})
    c.commit()
    rows = list(
        c.execute(
            "SELECT t.description, cat.name FROM transactions t"
            " LEFT JOIN categories cat ON cat.id = t.category_id ORDER BY t.date"
        )
    )
    assert [(r[0], r[1]) for r in rows] == [
        ("Lenta", "Groceries"),
        ("lenta market", "Groceries"),
    ]


def test_apply_reuses_existing_by_name_and_keeps_keywords(tmp_path):
    c, uid, acct = _db(tmp_path)
    c.execute(
        "INSERT INTO category_groups (user_id, name, sort, kind) VALUES (?, 'Daily', 9, 'expense')",
        (uid,),
    )
    gid = c.execute("SELECT id FROM category_groups").fetchone()[0]
    c.execute(
        "INSERT INTO categories (group_id, name, keywords, sort)"
        " VALUES (?, 'Groceries', 'mine', 4)",
        (gid,),
    )
    c.commit()
    result = apply_workbook(c, uid, _parsed(), {"": acct})
    c.commit()
    assert result["groupsCreated"] == 1
    assert result["categoriesCreated"] == 2
    row = c.execute("SELECT keywords, sort FROM categories WHERE name='Groceries'").fetchone()
    assert (row[0], row[1]) == ("mine", 4)
    cafes = c.execute("SELECT sort FROM categories WHERE name='Cafes'").fetchone()[0]
    assert cafes == 5


def test_apply_budget_policies(tmp_path):
    c, uid, acct = _db(tmp_path)
    apply_workbook(c, uid, _parsed(), {"": acct})
    c.commit()
    cid = c.execute("SELECT id FROM categories WHERE name='Groceries'").fetchone()[0]
    c.execute("UPDATE budgets SET amount=777 WHERE category_id=?", (cid,))
    c.commit()
    result = apply_workbook(c, uid, _parsed(), {"": acct}, budget_policy="skip")
    c.commit()
    assert result["budgetsWritten"] == 0
    assert result["budgetsSkipped"] == 2
    assert c.execute("SELECT amount FROM budgets WHERE category_id=?", (cid,)).fetchone()[0] == 777
    result = apply_workbook(c, uid, _parsed(), {"": acct}, budget_policy="overwrite")
    c.commit()
    assert result["budgetsWritten"] == 1
    assert (
        c.execute("SELECT amount FROM budgets WHERE category_id=?", (cid,)).fetchone()[0] == 20000
    )


def test_apply_batches_per_account_with_source(tmp_path):
    c, uid, acct = _db(tmp_path)
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'Second', 'card', 'RUB', 2)",
        (uid,),
    )
    c.commit()
    second = c.execute("SELECT id FROM accounts WHERE name='Second'").fetchone()[0]
    parsed = _parsed()
    parsed["transactions"][1]["marker"] = "*2"
    result = apply_workbook(c, uid, parsed, {"": acct, "*2": second})
    c.commit()
    assert len(result["batches"]) == 2
    assert {b["accountId"] for b in result["batches"]} == {acct, second}
    assert all(b["inserted"] == 1 for b in result["batches"])
    sources = {r[0] for r in c.execute("SELECT source FROM import_batches")}
    assert sources == {"workbook"}
    tx_sources = {r[0] for r in c.execute("SELECT source FROM transactions")}
    assert tx_sources == {"workbook"}


def test_apply_is_idempotent_on_rerun(tmp_path):
    c, uid, acct = _db(tmp_path)
    apply_workbook(c, uid, _parsed(), {"": acct})
    c.commit()
    result = apply_workbook(c, uid, _parsed(), {"": acct})
    c.commit()
    assert result["inserted"] == 0
    assert result["skipped"] == 2
    assert result["groupsCreated"] == 0
    assert result["categoriesCreated"] == 0
    assert c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2


def test_budget_conflicts_counts_only_matching_cells(tmp_path):
    c, uid, acct = _db(tmp_path)
    cells = _parsed()["budgets"]
    assert budget_conflicts(c, uid, cells) == 0

    apply_workbook(c, uid, _parsed(), {"": acct})
    c.commit()
    # Groceries 2026-01 now exists; the Ghost cell has no matching category.
    assert budget_conflicts(c, uid, cells) == 1
    assert budget_conflicts(c, uid, []) == 0

    other = [
        {"category": "Groceries", "year": 2026, "month": 2, "amount": 1},
        {"category": "Groceries", "year": 2027, "month": 1, "amount": 1},
        {"category": "Cafes", "year": 2026, "month": 1, "amount": 1},
    ]
    assert budget_conflicts(c, uid, other) == 0
