"""
Build normalized datasets + the golden reference from raw Sheets dumps.

Outputs into migration/out/:
  categories.json   — groups & categories with keywords/type as defined in Categories sheet
  budgets.json      — [{year, month, category, amount}] materialized budget values
  transactions.json — normalized real transactions
  reference.json    — per year/month: totals + per-category budgeted/outflows/balance
                      exactly as the Sheets formulas computed them (the parity contract)
"""

import json
import pathlib
from datetime import datetime, timedelta

RAW = pathlib.Path(__file__).parent / "raw"
OUT = pathlib.Path(__file__).parent / "out"
EPOCH = datetime(1899, 12, 30)

YEARS = list(range(2020, 2028))
GROUP_MARK = "▼▲"  # group names start with one of these


def load(name):
    return json.loads((RAW / f"{name}.json").read_text())


def serial_to_iso(serial):
    dt = EPOCH + timedelta(days=float(serial))
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def cell(rows, r, c, default=None):
    if r < len(rows) and c < len(rows[r]):
        v = rows[r][c]
        return default if v == "" else v
    return default


def build_categories():
    rows = load("categories")["unformatted_value"]
    groups = {}
    for r in rows[2:]:
        name = r[5] if len(r) > 5 else ""
        if name:
            groups[name] = {
                "name": name,
                "sort": int(r[6]),
                "type": r[7],
            }
    categories = []
    for r in rows[2:]:
        cat = r[2] if len(r) > 2 else ""
        if not cat:
            continue
        categories.append(
            {
                "name": cat,
                "group": r[1],
                "keywords": (r[3] if len(r) > 3 else "").strip(),
            }
        )
    return {"groups": sorted(groups.values(), key=lambda g: g["sort"]), "categories": categories}


def build_transactions():
    rows = load("transactions")["unformatted_value"]
    txs = []
    for i, r in enumerate(rows[1:], start=2):
        date = r[1] if len(r) > 1 else ""
        amount = r[7] if len(r) > 7 else ""
        if not isinstance(date, (int, float)) or not isinstance(amount, (int, float)):
            continue
        txs.append(
            {
                "row": i,
                "date": serial_to_iso(date),
                "amount": round(float(amount), 2),
                "bank_category": cell(rows, i - 1, 10, ""),
                "mcc": cell(rows, i - 1, 11, ""),
                "description": cell(rows, i - 1, 12, ""),
                "auto_category": cell(rows, i - 1, 16, ""),
                "category": cell(rows, i - 1, 17, ""),
                "comment": cell(rows, i - 1, 18, ""),
            }
        )
    return txs


def month_cols(m):  # m: 1..12 -> (budget, outflow, balance) 0-indexed cols
    base = 5 + 4 * (m - 1)
    return base, base + 2, base + 3


def build_year(year, vals):
    """
    Extract per-category monthly figures + totals for one year sheet.
    """
    out = {"year": year, "totals": {}, "groups": [], "rows": []}
    out["totals"] = {
        "income_total": cell(vals, 0, 3, 0),
        "outcome_total": cell(vals, 1, 3, 0),
        "income_by_month": [cell(vals, 2, 5 + 4 * m + 1, 0) for m in range(12)],
        "available_by_month": [cell(vals, 4, 5 + 4 * m + 1, 0) for m in range(12)],
    }
    # Blocks are detected dynamically: the first category row of each block has
    # the group index in column A; the block runs until the next group summary
    # row (whose C holds the group name) or the end of the sheet.
    first_rows = []
    for ri in range(8, len(vals)):
        a = cell(vals, ri, 0)
        if isinstance(a, (int, float)) and a == int(a) and 1 <= a <= 9:
            first_rows.append(ri)
    for bi, first_cat in enumerate(first_rows):
        gname = cell(vals, first_cat, 1)
        end = first_rows[bi + 1] - 1 if bi + 1 < len(first_rows) else len(vals)
        block_rows = []
        for ri in range(first_cat, end):
            cname = cell(vals, ri, 2)
            if cname is None or str(cname).startswith("#") or str(cname)[0] in GROUP_MARK:
                continue
            months = []
            for m in range(1, 13):
                bc, oc, blc = month_cols(m)
                months.append(
                    {
                        "budgeted": round(float(cell(vals, ri, bc, 0) or 0), 2),
                        "outflows": round(float(cell(vals, ri, oc, 0) or 0), 2),
                        "balance": round(float(cell(vals, ri, blc, 0) or 0), 2),
                    }
                )
            block_rows.append({"category": str(cname), "sheet_row": ri + 1, "months": months})
        if block_rows:
            out["groups"].append({"group": gname, "rows": block_rows})
            out["rows"].extend(block_rows)
    return out


def main():
    OUT.mkdir(exist_ok=True)
    cats = build_categories()
    txs = build_transactions()
    reference = {}
    budgets = []
    for y in YEARS:
        vals = load(f"year_{y}")["unformatted_value"]
        yr = build_year(y, vals)
        reference[str(y)] = yr
        for row in yr["rows"]:
            for m, mm in enumerate(row["months"], start=1):
                if mm["budgeted"]:
                    budgets.append(
                        {"year": y, "month": m, "category": row["category"], "amount": mm["budgeted"]}
                    )

    (OUT / "categories.json").write_text(json.dumps(cats, ensure_ascii=False, indent=1))
    (OUT / "transactions.json").write_text(json.dumps(txs, ensure_ascii=False))
    (OUT / "budgets.json").write_text(json.dumps(budgets, ensure_ascii=False, indent=1))
    (OUT / "reference.json").write_text(json.dumps(reference, ensure_ascii=False))

    print(f"groups: {len(cats['groups'])}, categories: {len(cats['categories'])}")
    print(f"transactions: {len(txs)} ({txs[0]['date']} .. {txs[-1]['date']})")
    print(f"budget cells (non-zero): {len(budgets)}")
    for y in YEARS:
        yr = reference[str(y)]
        ncat = len(yr["rows"])
        print(f"{y}: {ncat} category rows, groups: {[g['group'] for g in yr['groups']]}")


if __name__ == "__main__":
    main()
