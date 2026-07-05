"""Parity check: the SQLite database must reproduce the Sheets reference.

Checks per (year, month, category): outflows from transactions and budgeted
amounts; per (year, month): income totals. Exits non-zero on any mismatch.
"""

import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from app.db import connect

MIG_OUT = pathlib.Path(__file__).resolve().parent.parent / "migration" / "out"


def main(db_path=None):
    ref = json.loads((MIG_OUT / "reference.json").read_text())
    conn = connect(db_path)
    cur = conn.cursor()

    outflows = defaultdict(int)
    for r in cur.execute(
        """SELECT CAST(strftime('%Y', date) AS INT) y, CAST(strftime('%m', date) AS INT) m,
                  c.name, SUM(t.amount)
           FROM transactions t JOIN categories c ON c.id = t.category_id
           GROUP BY 1, 2, 3"""
    ):
        outflows[(r[0], r[1], r[2])] = r[3]

    budgets = {}
    for r in cur.execute(
        "SELECT b.year, b.month, c.name, b.amount FROM budgets b JOIN categories c ON c.id = b.category_id"
    ):
        budgets[(r[0], r[1], r[2])] = r[3]

    income_cats = {
        r[0]
        for r in cur.execute(
            "SELECT c.name FROM categories c JOIN category_groups g ON g.id = c.group_id WHERE g.kind='income'"
        )
    }
    income = defaultdict(int)
    for (y, m, cat), v in outflows.items():
        if cat in income_cats:
            income[(y, m)] += v

    errors = []
    checked = 0
    for ys, yr in ref.items():
        y = int(ys)
        for row in yr["rows"]:
            for mi, mm in enumerate(row["months"], 1):
                exp_out = round(mm["outflows"] * 100)
                got_out = outflows.get((y, mi, row["category"]), 0)
                if exp_out != got_out:
                    errors.append(f"outflow {y}-{mi:02d} {row['category']}: sheet {exp_out} db {got_out}")
                exp_b = round(mm["budgeted"] * 100)
                got_b = budgets.get((y, mi, row["category"]), 0)
                if exp_b != got_b:
                    errors.append(f"budget {y}-{mi:02d} {row['category']}: sheet {exp_b} db {got_b}")
                checked += 2
        for mi in range(1, 13):
            exp = yr["totals"]["income_by_month"][mi - 1]
            exp = round((exp if isinstance(exp, (int, float)) else 0) * 100)
            got = income.get((y, mi), 0)
            if exp != got:
                errors.append(f"income {y}-{mi:02d}: sheet {exp} db {got}")
            checked += 1

    print(f"checked {checked} figures, mismatches: {len(errors)}")
    for e in errors[:20]:
        print(" ", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
