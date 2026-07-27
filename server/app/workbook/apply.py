"""
Writes a parsed workbook (see ``importer.parse_workbook``) into the
database for one user. The caller owns the connection and the commit.
"""

import datetime

from ..ingest import commit_rows, drop_already_present, historical_day_counts
from .parser import account_slot


def _now():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _upsert_groups(c, uid, groups):
    existing = {
        r["name"]: r["id"]
        for r in c.execute("SELECT id, name FROM category_groups WHERE user_id=?", (uid,))
    }
    created = 0
    ids = {}
    for g in groups:
        if g["name"] in existing:
            ids[g["name"]] = existing[g["name"]]
            continue
        cur = c.execute(
            "INSERT INTO category_groups (user_id, name, sort, kind) VALUES (?, ?, ?, ?)",
            (uid, g["name"], g["sort"], g["kind"]),
        )
        ids[g["name"]] = cur.lastrowid
        created += 1
    return ids, created


def _upsert_categories(c, uid, categories, group_ids):
    existing = {
        (r["group_id"], r["name"]): r["id"]
        for r in c.execute(
            "SELECT c.id, c.group_id, c.name FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?",
            (uid,),
        )
    }
    max_sort = {
        r["group_id"]: r["s"]
        for r in c.execute(
            "SELECT c.group_id, MAX(c.sort) s FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?"
            " GROUP BY c.group_id",
            (uid,),
        )
    }
    created = 0
    ids = {}
    for cat in categories:
        gid = group_ids.get(cat["group"])
        if gid is None:
            continue
        key = (gid, cat["name"])
        if key in existing:
            ids[cat["name"]] = existing[key]
            continue
        sort = max_sort.get(gid, -1) + 1
        max_sort[gid] = sort
        cur = c.execute(
            "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, ?, ?, ?)",
            (gid, cat["name"], cat["keywords"], sort),
        )
        ids[cat["name"]] = cur.lastrowid
        created += 1
    return ids, created


def _category_index(c, uid):
    """
    Every category the user owns, keyed by a normalized name, so a workbook cell
    resolves against the whole account and not just the sheet's own category
    table. Names that collide across groups map to the first one by sort order —
    the workbook has no group column on the transaction row to tell them apart.
    """
    index: dict[str, int] = {}
    for r in c.execute(
        "SELECT c.id, c.name FROM categories c"
        " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?"
        " ORDER BY c.sort, c.id",
        (uid,),
    ):
        index.setdefault(_norm(r["name"]), r["id"])
    return index


def _norm(name):
    return " ".join(str(name).split()).casefold()


def _import_transactions(c, uid, transactions, mapping, category_ids):
    """
    A workbook is historical evidence, not a fresh bank feed: every category is
    copied exactly as it is written. In particular, a blank stays uncategorized.
    Imported keywords are retained for transactions added *after* migration,
    where the normal import/sync pipeline applies them.
    """
    index = _category_index(c, uid)
    # a sheet kept alongside a live sync describes the same operations the
    # sync already delivered — often onto a different account than the sheet's
    # card marker maps to, where the per-account hash cannot see them
    transactions, already = drop_already_present(transactions, historical_day_counts(c, uid))
    by_account: dict[int, list] = {}
    unmatched = set()
    blank = 0
    for tx in transactions:
        account_id = mapping[account_slot(tx)]
        named = tx["monori_category"]
        if named:
            category_id = category_ids.get(named) or index.get(_norm(named))
            if category_id is None:
                unmatched.add(named)
        else:
            category_id = None
            blank += 1
        row = {
            "date": tx["date"],
            "amount": tx["amount"],
            "currency": tx.get("currency"),
            "description": tx["description"],
            "bank_category": tx["bank_category"],
            "mcc": tx["mcc"],
            "category_id": category_id,
        }
        by_account.setdefault(account_id, []).append(row)
    inserted = skipped = 0
    batches = []
    for account_id, rows in sorted(by_account.items()):
        cur = c.execute(
            "INSERT INTO import_batches (account_id, source, created_at) VALUES (?, 'workbook', ?)",
            (account_id, _now()),
        )
        batch_id = cur.lastrowid
        ins, skip = commit_rows(c, account_id, rows, source="workbook", batch_id=batch_id)
        c.execute(
            "UPDATE import_batches SET inserted=?, skipped=? WHERE id=?", (ins, skip, batch_id)
        )
        inserted += ins
        skipped += skip
        batches.append({"accountId": account_id, "batchId": batch_id, "inserted": ins})
    return inserted, skipped + already, batches, sorted(unmatched), blank, already


def _import_budgets(c, budgets, category_ids, overwrite):
    written = skipped = 0
    for cell in budgets:
        cid = category_ids.get(cell["category"])
        if cid is None:
            skipped += 1
            continue
        if overwrite:
            c.execute(
                """INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)
                   ON CONFLICT(category_id, year, month) DO UPDATE SET amount=excluded.amount""",
                (cid, cell["year"], cell["month"], cell["amount"]),
            )
            written += 1
        else:
            cur = c.execute(
                """INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)
                   ON CONFLICT(category_id, year, month) DO NOTHING""",
                (cid, cell["year"], cell["month"], cell["amount"]),
            )
            if cur.rowcount:
                written += 1
            else:
                skipped += 1
    return written, skipped


def budget_conflicts(c, uid, budgets):
    """
    Count workbook budget cells that collide with the user's existing budgets
    (category matched by name, same year and month) — the only case where the
    overwrite/skip choice makes a difference.
    """
    existing = {
        (r["name"], r["year"], r["month"])
        for r in c.execute(
            "SELECT cat.name AS name, b.year AS year, b.month AS month FROM budgets b"
            " JOIN categories cat ON cat.id = b.category_id"
            " JOIN category_groups g ON g.id = cat.group_id WHERE g.user_id=?",
            (uid,),
        )
    }
    return sum(1 for cell in budgets if (cell["category"], cell["year"], cell["month"]) in existing)


def apply_workbook(c, uid, parsed, mapping, budget_policy="overwrite"):
    """
    ``mapping``: marker -> account id (all markers must be present and owned).
    Returns a result summary dict. Does not commit.
    """
    group_ids, groups_created = _upsert_groups(c, uid, parsed["groups"])
    category_ids, categories_created = _upsert_categories(c, uid, parsed["categories"], group_ids)
    inserted, skipped, batches, unmatched, blank, already = _import_transactions(
        c, uid, parsed["transactions"], mapping, category_ids
    )
    budgets_written, budgets_skipped = _import_budgets(
        c, parsed["budgets"], category_ids, budget_policy == "overwrite"
    )
    warnings = []
    if already:
        warnings.append(
            f"{already} rows are already in monori — delivered by a bank sync or an"
            " earlier import, possibly onto a different account — and were not"
            " imported again"
        )
    if blank:
        # the sheet's own totals leave these out too, so the budget is unaffected
        # — but they are a fifth of some ledgers and turn up as a wall of
        # uncategorized rows, which reads as a fault unless it is named
        warnings.append(
            f"{blank} rows carry no category in the sheet and were imported uncategorized"
            " — typically transfers between your own accounts, which the spreadsheet"
            " leaves out of the budget as well"
        )
    if unmatched:
        warnings.append(
            f"{len(unmatched)} category names in the sheet match nothing in monori"
            f" — those rows were left uncategorized rather than guessed:"
            f" {', '.join(unmatched[:10])}"
        )
    return {
        "groupsCreated": groups_created,
        "categoriesCreated": categories_created,
        "inserted": inserted,
        "skipped": skipped,
        "batches": batches,
        "budgetsWritten": budgets_written,
        "budgetsSkipped": budgets_skipped,
        "warnings": warnings,
    }
