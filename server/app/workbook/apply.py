"""
Writes a parsed workbook (see ``importer.parse_workbook``) into the
database for one user. The caller owns the connection and the commit.
"""

import datetime

from ..importer import build_rules, categorize
from ..ingest import commit_rows


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


def _user_rules(c, uid):
    groups = {
        r["id"]: r["kind"]
        for r in c.execute("SELECT id, kind FROM category_groups WHERE user_id=?", (uid,))
    }
    cats = [
        dict(r)
        for r in c.execute(
            "SELECT c.id, c.name, c.keywords, c.group_id FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=? ORDER BY c.sort",
            (uid,),
        )
    ]
    return build_rules(cats, groups)


def _import_transactions(c, uid, transactions, mapping, category_ids):
    rules = _user_rules(c, uid)
    by_account: dict[int, list] = {}
    for tx in transactions:
        account_id = mapping[tx["marker"]]
        category_id = category_ids.get(tx["monori_category"])
        if category_id is None:
            category_id = categorize(tx["description"], tx["amount"], rules)
        row = {
            "date": tx["date"],
            "amount": tx["amount"],
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
    return inserted, skipped, batches


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


def apply_workbook(c, uid, parsed, mapping, budget_policy="overwrite"):
    """
    ``mapping``: marker -> account id (all markers must be present and owned).
    Returns a result summary dict. Does not commit.
    """
    group_ids, groups_created = _upsert_groups(c, uid, parsed["groups"])
    category_ids, categories_created = _upsert_categories(c, uid, parsed["categories"], group_ids)
    inserted, skipped, batches = _import_transactions(
        c, uid, parsed["transactions"], mapping, category_ids
    )
    budgets_written, budgets_skipped = _import_budgets(
        c, parsed["budgets"], category_ids, budget_policy == "overwrite"
    )
    return {
        "groupsCreated": groups_created,
        "categoriesCreated": categories_created,
        "inserted": inserted,
        "skipped": skipped,
        "batches": batches,
        "budgetsWritten": budgets_written,
        "budgetsSkipped": budgets_skipped,
    }
