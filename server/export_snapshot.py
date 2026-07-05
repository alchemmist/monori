"""Dump the full data snapshot as JSON — same shape the /api/snapshot endpoint serves.

Used by the JS engine golden tests so they run against the exact migrated data.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from app.db import connect


def build_snapshot(conn):
    cur = conn.cursor()
    groups = [dict(r) for r in cur.execute("SELECT id, name, sort, kind FROM category_groups ORDER BY sort")]
    categories = [
        {
            "id": r["id"],
            "groupId": r["group_id"],
            "name": r["name"],
            "keywords": r["keywords"],
            "sort": r["sort"],
            "archived": bool(r["archived"]),
        }
        for r in cur.execute("SELECT * FROM categories ORDER BY sort")
    ]
    transactions = [
        {
            "id": r["id"],
            "date": r["date"],
            "amount": r["amount"],
            "description": r["description"],
            "bankCategory": r["bank_category"],
            "mcc": r["mcc"],
            "categoryId": r["category_id"],
            "comment": r["comment"],
            "source": r["source"],
        }
        for r in cur.execute("SELECT * FROM transactions ORDER BY date")
    ]
    budgets = [
        {"categoryId": r["category_id"], "year": r["year"], "month": r["month"], "amount": r["amount"]}
        for r in cur.execute("SELECT * FROM budgets")
    ]
    return {"groups": groups, "categories": categories, "transactions": transactions, "budgets": budgets}


if __name__ == "__main__":
    out = pathlib.Path(__file__).resolve().parent.parent / "migration" / "out" / "snapshot.json"
    conn = connect(sys.argv[1] if len(sys.argv) > 1 else None)
    out.write_text(json.dumps(build_snapshot(conn), ensure_ascii=False))
    print(f"snapshot -> {out}")
