"""Shared ingestion pipeline: turn parsed statement rows into transactions.

Both the manual paste import (``/api/import/commit``) and automated connector
syncs funnel through :func:`commit_rows`, so dedup and insertion behave
identically no matter where the rows came from. The hash is always recomputed
here and never trusted from the caller, so a re-submit or a re-sync can never
create duplicates.
"""

from .importer import build_rules, categorize, tx_hash

INSERT_SQL = """INSERT INTO transactions
   (date, amount, description, bank_category, mcc, category_id, account_id,
    batch_id, hash, source)
   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


def load_rules(c):
    """Build the IN/OUT categorization rules from the current categories."""
    groups = {r["id"]: r["kind"] for r in c.execute("SELECT id, kind FROM category_groups")}
    cats = [
        dict(r)
        for r in c.execute("SELECT id, name, keywords, group_id FROM categories ORDER BY sort")
    ]
    return build_rules(cats, groups)


def existing_hash_counts(c):
    return {
        r["hash"]: r["n"]
        for r in c.execute("SELECT hash, COUNT(*) n FROM transactions GROUP BY hash")
    }


def commit_rows(c, account_id, rows, source, batch_id=None):
    """Insert ``rows`` (dicts with date/amount/description/bank_category/mcc and
    an optional category_id) onto ``account_id``, skipping any whose hash is
    already present in the DB or repeats within this batch. Does not commit — the
    caller owns the transaction. Returns ``(inserted, skipped)``."""
    existing = existing_hash_counts(c)
    seen: dict = {}
    inserted = skipped = 0
    for r in rows:
        h = tx_hash(r["date"], r["amount"], r["description"])
        n_batch = seen.get(h, 0)
        seen[h] = n_batch + 1
        if n_batch < existing.get(h, 0):
            skipped += 1
            continue
        c.execute(
            INSERT_SQL,
            (
                r["date"],
                r["amount"],
                r.get("description", ""),
                r.get("bank_category", ""),
                r.get("mcc", ""),
                r.get("category_id"),
                account_id,
                batch_id,
                h,
                source,
            ),
        )
        inserted += 1
    return inserted, skipped


def categorize_rows(rows, rules):
    """Fill ``category_id`` on each row in place using the given rules."""
    for r in rows:
        r["category_id"] = categorize(r["description"], r["amount"], rules)
    return rows
