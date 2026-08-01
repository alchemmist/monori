"""
Shared ingestion pipeline: turn parsed statement rows into transactions.

Both the manual paste import (``/api/import/commit``) and automated connector
syncs funnel through :func:`commit_rows`, so dedup and insertion behave
identically no matter where the rows came from. The hash is always recomputed
here and never trusted from the caller, so a re-submit or a re-sync can never
create duplicates.
"""

import sqlite3
from collections.abc import Iterable, Mapping

from .connectors.base import SyncRow
from .importer import CategoryDefinition, CategoryRule, build_rules, categorize, tx_hash

INSERT_SQL = """INSERT INTO transactions
   (date, amount, description, bank_category, mcc, category_id, account_id,
    batch_id, hash, source)
   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


def load_rules(c: sqlite3.Connection) -> dict[str, list[CategoryRule]]:
    """
    Build the IN/OUT categorization rules from the current categories.
    """
    groups = {
        r["id"]: r["kind"]
        for r in c.execute(
            "SELECT g.id, t.type AS kind FROM category_groups g"
            " JOIN category_group_types t ON t.id=g.type_id"
        )
    }
    cats: list[CategoryDefinition] = [
        CategoryDefinition(
            id=int(r["id"]),
            name=str(r["name"]),
            keywords=str(r["keywords"]) if r["keywords"] is not None else None,
            group_id=int(r["group_id"]),
        )
        for r in c.execute("SELECT id, name, keywords, group_id FROM categories ORDER BY sort")
    ]
    return build_rules(cats, groups)


def existing_hash_counts(c: sqlite3.Connection, account_id: int) -> dict[str, int]:
    """
    Hash → count of matching transactions on ``account_id``. Dedup is scoped
    per account so the same date/amount/description legitimately occurring on two
    different accounts is not collapsed away.
    """
    return {
        r["hash"]: r["n"]
        for r in c.execute(
            "SELECT hash, COUNT(*) n FROM transactions WHERE account_id=? GROUP BY hash",
            (account_id,),
        )
    }


def dedup_text(description: str) -> str:
    """
    The bank's own wording drifts between pulls — a pending operation can gain
    or lose punctuation once it posts, and one character of drift is enough to
    slip past an exact-text key. Case, punctuation and extra whitespace are
    cosmetic; only the letters and digits identify the operation.
    """
    kept = "".join(ch if ch.isalnum() else " " for ch in str(description or "").lower())
    return " ".join(kept.split())


def historical_day_counts(
    c: sqlite3.Connection,
    uid: int,
    sources: tuple[str, ...] = ("workbook", "import", "sync", "sheets"),
) -> dict[tuple[str, int, str], int]:
    """
    ``(day, amount, normalized description) -> count`` over every transaction
    the user got from a statement-shaped source, across all accounts. The
    per-account hash cannot see the same bank operation arriving a second time
    through another door — a workbook over a synced ledger, or one connection
    pulling overlapping feeds — because the copies land on different accounts
    or carry different times. By calendar day and without the account, the
    copies collide. Manual entries and transfer legs are left out: they are
    the user's own words, not a bank's, and must never shadow a feed.
    ``sheets`` is the retired template importer's label — those rows are still
    in the wild and are statement-shaped all the same.
    """
    marks = ",".join("?" * len(sources))
    counts: dict[tuple[str, int, str], int] = {}
    for r in c.execute(
        "SELECT substr(t.date, 1, 10) day, t.amount, t.description, COUNT(*) n"
        " FROM transactions t JOIN accounts a ON a.id = t.account_id"
        # `marks` contains only generated positional placeholders, never user input.
        f" WHERE a.user_id=? AND t.source IN ({marks})"  # nosec B608
        " GROUP BY day, t.amount, t.description",
        (uid, *sources),
    ):
        key = (str(r["day"]), int(r["amount"]), dedup_text(str(r["description"])))
        counts[key] = counts.get(key, 0) + int(r["n"])
    return counts


def drop_already_present(
    rows: Iterable[SyncRow], counts: Mapping[tuple[str, int, str], int]
) -> tuple[list[SyncRow], int]:
    """
    Drop rows the ledger already holds according to ``counts``, counting
    repeats: two genuinely identical operations in one batch survive as long
    as the ledger holds fewer copies than the batch carries. Returns
    ``(kept, dropped)``.
    """
    seen: dict[tuple[str, int, str], int] = {}
    kept: list[SyncRow] = []
    dropped = 0
    for row in rows:
        key = (row.date[:10], row.amount, dedup_text(row.description))
        n = seen.get(key, 0)
        seen[key] = n + 1
        if n < counts.get(key, 0):
            dropped += 1
            continue
        kept.append(row)
    return kept, dropped


def commit_rows(
    c: sqlite3.Connection,
    account_id: int,
    rows: Iterable[SyncRow],
    source: str,
    batch_id: int | None = None,
) -> tuple[int, int]:
    """
    Insert ``rows`` (dicts with date/amount/description/bank_category/mcc and
    an optional category_id) onto ``account_id``, skipping any whose hash is
    already present on that account or repeats within this batch. Does not commit
    — the caller owns the transaction. Returns ``(inserted, skipped)``.
    """
    existing = existing_hash_counts(c, account_id)
    seen: dict[str, int] = {}
    inserted = skipped = 0
    for r in rows:
        h = tx_hash(account_id, r.date, r.amount, r.description)
        n_batch = seen.get(h, 0)
        seen[h] = n_batch + 1
        if n_batch < existing.get(h, 0):
            skipped += 1
            continue
        c.execute(
            INSERT_SQL,
            (
                r.date,
                r.amount,
                r.description,
                r.bank_category,
                r.mcc,
                r.category_id,
                account_id,
                batch_id,
                h,
                source,
            ),
        )
        inserted += 1
    return inserted, skipped


def categorize_rows(
    rows: list[SyncRow],
    rules: Mapping[str, list[CategoryRule]],
) -> list[SyncRow]:
    """
    Fill ``category_id`` on each row in place using the given rules.
    """
    for r in rows:
        r.category_id = categorize(r.description, r.amount, rules)
    return rows
