"""
One-shot migration: load migration/out/*.json into the SQLite database.

Money is converted to integer kopecks. The three manual Loans adjustments
found in the 2026 sheet formulas are materialized as adjustment transactions
so that outflow parity with the sheet holds.
"""

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from app.db import connect

MIG_OUT = pathlib.Path(__file__).resolve().parent.parent / "migration" / "out"

GROUP_KIND = {"IN": "income", "OUT": "expense"}

# (year, month, category, rubles) — hand-written tails found in sheet formulas
MANUAL_ADJUSTMENTS = [
    (2026, 2, "Loans", -1035.0),
    (2026, 3, "Loans", -1035.0),
    (2026, 4, "Loans", -1035.0),
]


def kop(rubles):
    return round(round(float(rubles), 2) * 100)


def tx_hash(date, amount_kop, description):
    return hashlib.sha1(
        f"{date}|{amount_kop}|{description}".encode(), usedforsecurity=False
    ).hexdigest()


def main(db_path=None):
    cats = json.loads((MIG_OUT / "categories.json").read_text())
    txs = json.loads((MIG_OUT / "transactions.json").read_text())
    budgets = json.loads((MIG_OUT / "budgets.json").read_text())

    conn = connect(db_path)
    cur = conn.cursor()
    account_id = cur.execute("SELECT MIN(id) FROM accounts").fetchone()[0]
    counts = {
        t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("category_groups", "categories", "transactions", "budgets")
    }
    if any(counts.values()):
        print(f"database is not empty ({counts}), refusing to migrate", file=sys.stderr)
        sys.exit(1)

    group_ids = {}
    for g in cats["groups"]:
        name = g["name"].lstrip("▼▲")
        cur.execute(
            "INSERT INTO category_groups (name, sort, kind) VALUES (?, ?, ?)",
            (name, g["sort"], GROUP_KIND[g["type"]]),
        )
        group_ids[g["name"]] = cur.lastrowid

    cat_ids = {}
    for i, c in enumerate(cats["categories"]):
        cur.execute(
            "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, ?, ?, ?)",
            (group_ids[c["group"]], c["name"], c["keywords"], i),
        )
        cat_ids[c["name"]] = cur.lastrowid

    for t in txs:
        amount = kop(t["amount"])
        cur.execute(
            """INSERT INTO transactions
               (date, amount, description, bank_category, mcc, category_id, account_id,
                comment, hash, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'sheets')""",
            (
                t["date"],
                amount,
                str(t["description"]),
                str(t["bank_category"]),
                str(t["mcc"]),
                cat_ids.get(t["category"]),
                account_id,
                str(t["comment"]),
                tx_hash(t["date"], amount, str(t["description"])),
            ),
        )

    for y, m, cat, rub in MANUAL_ADJUSTMENTS:
        date = f"{y}-{m:02d}-15T12:00:00"
        amount = kop(rub)
        desc = "Manual adjustment carried over from sheet formula"
        cur.execute(
            """INSERT INTO transactions
               (date, amount, description, category_id, account_id, hash, source)
               VALUES (?, ?, ?, ?, ?, ?, 'adjustment')""",
            (date, amount, desc, cat_ids[cat], account_id, tx_hash(date, amount, desc)),
        )

    for b in budgets:
        cur.execute(
            "INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)",
            (cat_ids[b["category"]], b["year"], b["month"], kop(b["amount"])),
        )

    conn.commit()
    for t in ("category_groups", "categories", "transactions", "budgets"):
        print(t, cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    conn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
