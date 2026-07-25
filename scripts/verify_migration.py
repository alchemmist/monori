"""
End-to-end migration parity: import a workbook the way the server does, then
check that the budget monori shows equals the one the spreadsheet cached.

    uv run --project server python scripts/verify_migration.py book.xlsx

Runs the real path — ``parse_workbook`` into ``apply_workbook`` against a
throwaway database — reads the snapshot back out, replays the client's budget
engine on it, and diffs every category/month cell (budgeted, outflows, balance)
plus the running Available against the numbers the sheet computed for itself.
Also reports duplicate rows and anything imported uncategorized. Exits non-zero
when a cell disagrees, so it can guard a change to the importer.

Nothing outside the temporary database is written; the workbook is only read.
"""

import argparse
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "server"))

from app.db import connect  # noqa: E402
from app.workbook.apply import apply_workbook  # noqa: E402
from app.workbook.parser import (  # noqa: E402
    YEAR_RE,
    _find_layout,
    _parse_year_sheet,
    _s,
    _summary_value,
    account_slot,
    parse_workbook,
)
from openpyxl import load_workbook  # noqa: E402

MONEY = 100


def rub(kop):
    return "." if kop is None else f"{kop / MONEY:,.2f}"


def sheet_grids(path):
    """Year grids keyed by year, plus the header figures, as the sheet cached them."""
    wb = load_workbook(path, data_only=True)
    try:
        grids, headers = {}, {}
        for name in wb.sheetnames:
            match = YEAR_RE.match(name)
            if not match:
                continue
            ws = wb[name]
            layout = _find_layout(ws)
            if layout is None:
                continue
            year = int(match.group(1))
            if match.group(2) and year in grids:
                continue  # a plain sheet is the working copy and wins
            grids[year] = _parse_year_sheet(ws, year, layout)
            for i, base in enumerate(layout["bases"]):
                month = layout["start_month"] + i
                if month > 12:
                    break
                headers[(year, month)] = {
                    "overspent": _summary_value(ws, base, ("Overspent in", "Перерасход")),
                    "budgeted": _summary_value(ws, base, ("Budgeted in", "Заложено")),
                    "income": _summary_value(ws, base, ("Income for", "Поступления в")),
                    "carried": _summary_value(ws, base, ("Not budgeted", "Не заложено")),
                    "available": _available(ws, base),
                }
        return grids, headers
    finally:
        wb.close()


def _available(ws, base):
    for r in (5, 6):
        if _s(ws.cell(r + 1, base + 1).value).startswith(("Available", "Доступный")):
            from app.workbook.parser import _kop

            return _kop(ws.cell(r, base + 1).value)
    return None


def import_into_db(path, db_path):
    """The server's own path: parse, map every slot onto a matching account, apply."""
    parsed = parse_workbook(pathlib.Path(path).read_bytes())
    c = connect(db_path)
    c.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('parity@local', 'parity@local', 'x', '2020-01-01')"
    )
    uid = c.execute("SELECT id FROM users").fetchone()["id"]
    mapping = {}
    for row in parsed["transactions"]:
        key = account_slot(row)
        if key in mapping:
            continue
        currency = key.split(":", 1)[0]
        cur = c.execute(
            "INSERT INTO accounts (user_id, name, currency) VALUES (?, ?, ?)",
            (uid, key, currency),
        )
        mapping[key] = cur.lastrowid
    result = apply_workbook(c, uid, parsed, mapping, "overwrite")
    c.commit()
    return c, uid, parsed, result


def snapshot(c, uid):
    kinds = {
        r["id"]: r["kind"]
        for r in c.execute("SELECT id, kind FROM category_groups WHERE user_id=?", (uid,))
    }
    cats = {
        r["id"]: (r["name"], kinds.get(r["group_id"], "expense"))
        for r in c.execute(
            "SELECT c.id, c.name, c.group_id FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?",
            (uid,),
        )
    }
    tx: dict[tuple, int] = {}
    uncategorized = 0
    for r in c.execute(
        "SELECT t.date, t.amount, t.category_id FROM transactions t"
        " JOIN accounts a ON a.id = t.account_id WHERE a.user_id=? AND t.transfer_id IS NULL",
        (uid,),
    ):
        if r["category_id"] is None:
            uncategorized += 1
            continue
        name = cats[r["category_id"]][0]
        key = (name, int(r["date"][:4]), int(r["date"][5:7]))
        tx[key] = tx.get(key, 0) + r["amount"]
    budgets: dict[tuple, int] = {}
    for r in c.execute(
        "SELECT b.year, b.month, b.amount, c.name FROM budgets b"
        " JOIN categories c ON c.id = b.category_id"
        " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?",
        (uid,),
    ):
        budgets[(r["name"], r["year"], r["month"])] = r["amount"]
    return cats, tx, budgets, uncategorized


def duplicates(c, uid):
    """Rows a human would read as the same entry twice on one account."""
    return [
        (r["name"], r["date"], r["amount"], r["description"], r["n"])
        for r in c.execute(
            "SELECT a.name, t.date, t.amount, t.description, COUNT(*) n"
            " FROM transactions t JOIN accounts a ON a.id = t.account_id"
            " WHERE a.user_id=? GROUP BY t.account_id, t.date, t.amount, t.description"
            " HAVING n > 1 ORDER BY n DESC, t.date",
            (uid,),
        )
    ]


def _header_adds_up(head):
    """
    Whether the month's own header cells make its Available: carried over +
    overspent + income - budgeted. The template's formula has been edited by
    hand over the years and in places dropped a term, so a month can disagree
    with itself; monori applies the envelope rule to every month alike.
    """
    parts = [head.get(k) for k in ("carried", "overspent", "income", "budgeted")]
    if head.get("available") is None or any(p is None for p in parts):
        return None
    return abs(sum(parts) - head["available"]) <= 5


def _carried_overspend(grids, head, year, month):
    """
    Whether the month's "Overspent in <previous>" cell equals what the previous
    month's own Balance column actually adds up to. A cell whose formula was
    repointed and never recalculated keeps a figure from a different month.
    """
    cached = head.get("overspent")
    if cached is None:
        return None
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    grid = grids.get(prev_year)
    if grid is None or prev_month not in grid["months"]:
        return None
    total = sum(min(entry["balances"].get(prev_month, 0), 0) for entry in grid["cats"].values())
    return abs(total - cached) <= 2


def _self_consistent(grids, name, year, month):
    """
    Whether the sheet's own three numbers for this cell agree with each other:
    carried balance + budgeted + outflows == balance. When they do not, the cell
    is a stale cache in the spreadsheet and monori follows the balance, which is
    the figure the sheet displays and carries forward.
    """
    entry = grids[year]["cats"].get(name)
    if entry is None:
        return None
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    prev = (
        grids.get(prev_year, {}).get("cats", {}).get(name, {}).get("balances", {}).get(prev_month)
    )
    budgeted = entry["budgets"].get(month)
    outflows = entry["outflows"].get(month)
    balance = entry["balances"].get(month)
    if None in (budgeted, outflows, balance):
        return None
    return abs(max(prev or 0, 0) + budgeted + outflows - balance) <= 2


def replay(cats, tx, budgets, first_year, last_year):
    """web/src/engine/budget.js, on what the database actually holds."""
    expense = sorted({n for n, k in cats.values() if k != "income"})
    income_cats = sorted({n for n, k in cats.values() if k == "income"})
    balances: dict[str, int] = {}
    avail = 0
    prev_overspent = 0
    out = {}
    for year in range(first_year, last_year + 1):
        for m in range(1, 13):
            income = sum(tx.get((n, year, m), 0) for n in income_cats)
            budgeted = sum(budgets.get((n, year, m), 0) for n in expense)
            overspent = 0
            cells = {}
            for n in expense:
                bal = (
                    max(balances.get(n, 0), 0)
                    + budgets.get((n, year, m), 0)
                    + tx.get((n, year, m), 0)
                )
                balances[n] = bal
                if bal < 0:
                    overspent += bal
                cells[n] = {
                    "budgeted": budgets.get((n, year, m), 0),
                    "outflows": tx.get((n, year, m), 0),
                    "balance": bal,
                }
            avail = avail + prev_overspent + income - budgeted
            prev_overspent = overspent
            out[(year, m)] = {
                "income": income,
                "budgeted": budgeted,
                "overspent": overspent,
                "available": avail,
                "cells": cells,
            }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workbook")
    ap.add_argument("--report", default="", help="write the full mismatch list here")
    ap.add_argument("--limit", type=int, default=25, help="mismatches to print per section")
    args = ap.parse_args()

    grids, headers = sheet_grids(args.workbook)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(pathlib.Path(tmp) / "parity.db")
        c, uid, parsed, result = import_into_db(args.workbook, db_path)
        cats, tx, budgets, uncategorized = snapshot(c, uid)
        dupes = duplicates(c, uid)
        c.close()

    years = sorted(grids)
    first_year = min(
        [*(y for _, y, _ in tx), *(y for _, y, _ in budgets), *years] or [years[0] if years else 0]
    )
    replayed = replay(cats, tx, budgets, first_year, max(years))

    lines = []
    bad_cells = []
    for year in years:
        grid = grids[year]
        for name, entry in grid["cats"].items():
            for m in grid["months"]:
                ours = replayed[(year, m)]["cells"].get(name)
                if ours is None:
                    continue  # income rows have no envelope; checked via the totals
                for field, column in (
                    ("budgeted", "budgets"),
                    ("outflows", "outflows"),
                    ("balance", "balances"),
                ):
                    want = entry[column].get(m)
                    if want is None:
                        continue
                    if abs(want - ours[field]) > 2:
                        bad_cells.append(
                            (
                                year,
                                m,
                                name,
                                field,
                                want,
                                ours[field],
                                _self_consistent(grids, name, year, m),
                            )
                        )

    # Available is a running total, so a gap opened once is repeated by every
    # later month. Only the months where it *changes* say anything.
    bad_months = []
    carried_gap = 0
    for (year, m), head in sorted(headers.items()):
        ours = replayed.get((year, m))
        want = head.get("available")
        if ours is None or want is None:
            continue
        gap = want - ours["available"]
        if abs(gap - carried_gap) > 5:
            stale = _header_adds_up(head)
            if stale is not False and _carried_overspend(grids, head, year, m) is False:
                stale = False
            bad_months.append((year, m, want, ours["available"], gap - carried_gap, stale))
        carried_gap = gap

    lines.append(f"transactions imported : {result['inserted']}")
    lines.append(f"skipped as duplicate  : {result['skipped']}")
    lines.append(f"budget cells written  : {result['budgetsWritten']}")
    lines.append(f"budget cells skipped  : {result['budgetsSkipped']}")
    lines.append(f"rows left uncategorized: {uncategorized}")
    lines.append(f"duplicate row groups  : {len(dupes)}")
    lines.append(f"grid cells wrong      : {len(bad_cells)}")
    lines.append(f"months where the Available gap changes: {len(bad_months)}")
    lines.append("")
    for w in [*parsed["warnings"], *result["warnings"]]:
        lines.append(f"  warning: {w}")
    if dupes:
        lines.append("\n-- duplicate rows (account, date, amount, description, count) --")
        lines += [f"  {a} {d[:10]} {rub(v):>14} {desc[:40]!r} x{n}" for a, d, v, desc, n in dupes]
    if bad_cells:
        lines.append("\n-- grid cells: sheet vs monori --")
        lines.append("   'sheet stale' = the sheet's own budgeted+outflows do not make its balance")
        lines += [
            f"  {y}-{m:02d} {n[:28]:<28} {f:<9} sheet {rub(w):>14}  ours {rub(g):>14}"
            f"  d {rub(w - g):>12}  {'sheet stale' if ok is False else ''}"
            for y, m, n, f, w, g, ok in bad_cells
        ]
    if bad_months:
        lines.append("\n-- Available: months where the gap to the sheet changes --")
        lines.append("   'sheet stale' = the sheet's own header cells do not make its own total")
        lines += [
            f"  {y}-{m:02d} sheet {rub(w):>16}  ours {rub(g):>16}  gap opened {rub(d):>14}"
            f"  {'sheet stale' if ok is False else ''}"
            for y, m, w, g, d, ok in bad_months
        ]

    text = "\n".join(lines)
    if args.report:
        pathlib.Path(args.report).write_text(text + "\n")
    head, *rest = text.split("\n\n", 1)
    print(head)
    if rest:
        body = rest[0].split("\n")
        print("\n".join(body[: args.limit]))
        if len(body) > args.limit:
            print(
                f"  … {len(body) - args.limit} more lines"
                + (f" in {args.report}" if args.report else "")
            )
    return 1 if bad_cells or bad_months or dupes or uncategorized else 0


if __name__ == "__main__":
    sys.exit(main())
