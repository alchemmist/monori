"""
Writes a parsed workbook (see ``importer.parse_workbook``) into the
database for one user. The caller owns the connection and the commit.
"""

import datetime
import sqlite3
from collections.abc import Iterable, Mapping
from typing import cast

from ..importer import ImportRow
from ..ingest import commit_rows, dedup_text, historical_day_counts
from .models import (
    ParsedWorkbook,
    WorkbookApplyResult,
    WorkbookBatchResult,
    WorkbookBudget,
    WorkbookCategory,
    WorkbookGroup,
    WorkbookTransaction,
)
from .parser import account_slot


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _upsert_groups(
    c: sqlite3.Connection, uid: int, groups: Iterable[WorkbookGroup]
) -> tuple[dict[str, int], int]:
    existing = {
        cast("str", r["name"]): cast("int", r["id"])
        for r in c.execute("SELECT id, name FROM category_groups WHERE user_id=?", (uid,))
    }
    created = 0
    ids: dict[str, int] = {}
    for g in groups:
        if g.name in existing:
            ids[g.name] = existing[g.name]
            continue
        cur = c.execute(
            "INSERT INTO category_groups (user_id, name, sort, type_id)"
            " VALUES (?, ?, ?, (SELECT id FROM category_group_types WHERE type=?))",
            (uid, g.name, g.sort, g.kind),
        )
        ids[g.name] = cast("int", cur.lastrowid)
        created += 1
    return ids, created


def _upsert_categories(
    c: sqlite3.Connection,
    uid: int,
    categories: Iterable[WorkbookCategory],
    group_ids: Mapping[str, int],
) -> tuple[dict[str, int], int]:
    existing = {
        (cast("int", r["group_id"]), cast("str", r["name"])): cast("int", r["id"])
        for r in c.execute(
            "SELECT c.id, c.group_id, c.name FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?",
            (uid,),
        )
    }
    max_sort = {
        cast("int", r["group_id"]): cast("int", r["s"])
        for r in c.execute(
            "SELECT c.group_id, MAX(c.sort) s FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?"
            " GROUP BY c.group_id",
            (uid,),
        )
    }
    created = 0
    ids: dict[str, int] = {}
    for cat in categories:
        gid = group_ids.get(cat.group)
        if gid is None:
            continue
        key = (gid, cat.name)
        if key in existing:
            ids[cat.name] = existing[key]
            continue
        sort = max_sort.get(gid, -1) + 1
        max_sort[gid] = sort
        cur = c.execute(
            "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, ?, ?, ?)",
            (gid, cat.name, cat.keywords, sort),
        )
        ids[cat.name] = cast("int", cur.lastrowid)
        created += 1
    return ids, created


def _category_index(c: sqlite3.Connection, uid: int) -> dict[str, int]:
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
        index.setdefault(_norm(cast("str", r["name"])), cast("int", r["id"]))
    return index


def _norm(name: str) -> str:
    return " ".join(name.split()).casefold()


def _drop_already_present(
    rows: Iterable[WorkbookTransaction], counts: Mapping[tuple[str, object, str], int]
) -> tuple[list[WorkbookTransaction], int]:
    seen: dict[tuple[str, object, str], int] = {}
    kept: list[WorkbookTransaction] = []
    dropped = 0
    for row in rows:
        key = (row.date[:10], row.amount, dedup_text(row.description))
        n = seen.get(key, 0)
        seen[key] = n + 1
        if n < counts.get(key, 0):
            dropped += 1
        else:
            kept.append(row)
    return kept, dropped


def _import_transactions(
    c: sqlite3.Connection,
    uid: int,
    transactions: Iterable[WorkbookTransaction],
    mapping: Mapping[str, int],
    category_ids: Mapping[str, int],
) -> tuple[int, int, list[WorkbookBatchResult], list[str], int, int]:
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
    transactions, already = _drop_already_present(transactions, historical_day_counts(c, uid))
    by_account: dict[int, list[ImportRow]] = {}
    unmatched: set[str] = set()
    blank = 0
    for tx in transactions:
        account_id = mapping[account_slot(tx)]
        named = tx.monori_category
        if named:
            category_id = category_ids.get(named) or index.get(_norm(named))
            if category_id is None:
                unmatched.add(named)
        else:
            category_id = None
            blank += 1
        row = ImportRow(
            date=tx.date,
            amount=tx.amount,
            description=tx.description,
            bank_category=tx.bank_category,
            mcc=tx.mcc,
            card=tx.marker,
            category_id=category_id,
        )
        by_account.setdefault(account_id, []).append(row)
    inserted = skipped = 0
    batches: list[WorkbookBatchResult] = []
    for account_id, rows in sorted(by_account.items()):
        cur = c.execute(
            "INSERT INTO import_batches (account_id, source, created_at) VALUES (?, 'workbook', ?)",
            (account_id, _now()),
        )
        batch_id = cast("int", cur.lastrowid)
        ins, skip = commit_rows(
            c,
            account_id,
            [row.to_ingest_dict() for row in rows],
            source="workbook",
            batch_id=batch_id,
        )
        c.execute(
            "UPDATE import_batches SET inserted=?, skipped=? WHERE id=?", (ins, skip, batch_id)
        )
        inserted += ins
        skipped += skip
        batches.append(WorkbookBatchResult(account_id, batch_id, ins))
    return inserted, skipped + already, batches, sorted(unmatched), blank, already


def _import_budgets(
    c: sqlite3.Connection,
    budgets: Iterable[WorkbookBudget],
    category_ids: Mapping[str, int],
    overwrite: bool,
) -> tuple[int, int]:
    written = skipped = 0
    for cell in budgets:
        cid = category_ids.get(cell.category)
        if cid is None:
            skipped += 1
            continue
        if overwrite:
            c.execute(
                """INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)
                   ON CONFLICT(category_id, year, month) DO UPDATE SET amount=excluded.amount""",
                (cid, cell.year, cell.month, cell.amount),
            )
            written += 1
        else:
            cur = c.execute(
                """INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)
                   ON CONFLICT(category_id, year, month) DO NOTHING""",
                (cid, cell.year, cell.month, cell.amount),
            )
            if cur.rowcount:
                written += 1
            else:
                skipped += 1
    return written, skipped


def budget_conflicts(
    c: sqlite3.Connection, uid: int, budgets: Iterable[WorkbookBudget]
) -> int:
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
    return sum(1 for cell in budgets if (cell.category, cell.year, cell.month) in existing)


def apply_workbook(
    c: sqlite3.Connection,
    uid: int,
    parsed: ParsedWorkbook,
    mapping: Mapping[str, int],
    budget_policy: str = "overwrite",
) -> WorkbookApplyResult:
    """
    ``mapping``: marker -> account id (all markers must be present and owned).
    Returns a result summary dict. Does not commit.
    """
    group_ids, groups_created = _upsert_groups(c, uid, parsed.groups)
    category_ids, categories_created = _upsert_categories(c, uid, parsed.categories, group_ids)
    inserted, skipped, batches, unmatched, blank, already = _import_transactions(
        c, uid, parsed.transactions, mapping, category_ids
    )
    budgets_written, budgets_skipped = _import_budgets(
        c, parsed.budgets, category_ids, budget_policy == "overwrite"
    )
    warnings: list[str] = []
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
    return WorkbookApplyResult(
        groups_created=groups_created,
        categories_created=categories_created,
        inserted=inserted,
        skipped=skipped,
        batches=batches,
        budgets_written=budgets_written,
        budgets_skipped=budgets_skipped,
        warnings=warnings,
    )
