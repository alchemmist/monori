# Copyright (c) 2026
"""
The glue between a stored amount and what it is worth.

Three questions get asked all over the write paths — what currency is this
account held in, what currency does this user report in, and what is this
amount worth in that reporting currency on that day — and they are answered
here so every path answers them the same way.
"""

import sqlite3
from collections.abc import Iterable

from .currencies import DEFAULT_CURRENCY, normalize
from .rates import convert, today_iso


def account_currency(c: sqlite3.Connection, account_id: int) -> str:
    """Return the currency in which an account is held."""
    row = c.execute("SELECT currency FROM accounts WHERE id=?", (account_id,)).fetchone()
    return normalize(row["currency"] if row else None)


def base_currency(c: sqlite3.Connection, user_id: int) -> str:
    """Return a user's reporting currency."""
    row = c.execute("SELECT base_currency FROM users WHERE id=?", (user_id,)).fetchone()
    return normalize(row["base_currency"] if row else None)


def base_currency_of_account(c: sqlite3.Connection, account_id: int) -> str:
    """
    Return the reporting currency of whoever owns this account.

    Ingestion knows the
    account it is writing to long before it knows the user.
    """
    row = c.execute(
        "SELECT u.base_currency FROM accounts a JOIN users u ON u.id = a.user_id WHERE a.id=?",
        (account_id,),
    ).fetchone()
    return normalize(row["base_currency"] if row else None)


def to_base(
    c: sqlite3.Connection,
    amount: int,
    currency: str,
    base: str,
    date: str,
) -> int:
    """
    ``amount`` in ``base``, at the rate for ``date``.

    Missing historical rates fail explicitly so incomparable units can never be
    stored as though they were equal.
    """
    if amount == 0:
        return 0
    return convert(c, amount, currency, base, date)


def resolve_currency(c: sqlite3.Connection, account_id: int, requested: str | None) -> str:
    """
    Resolve what a new transaction on this account is denominated in.

    Prefer what the caller
    asked for, else the account's own currency, else rubles.
    """
    code = normalize(requested, "")
    return code or account_currency(c, account_id) or DEFAULT_CURRENCY


def validate_account_valuations(
    c: sqlite3.Connection,
    account_ids: Iterable[int],
) -> None:
    """Ensure affected accounts can be valued before their write is committed."""
    for account_id in set(account_ids):
        account = c.execute(
            "SELECT a.currency, a.opening_balance, a.opening_date, u.base_currency"
            " FROM accounts a JOIN users u ON u.id=a.user_id WHERE a.id=?",
            (account_id,),
        ).fetchone()
        if account is None:
            continue
        first_date = c.execute(
            "SELECT MIN(date) FROM transactions WHERE account_id=?",
            (account_id,),
        ).fetchone()[0]
        effective_date = account["opening_date"] or first_date or today_iso()
        to_base(
            c,
            account["opening_balance"],
            account["currency"],
            account["base_currency"],
            effective_date,
        )
        for row in c.execute(
            "SELECT DISTINCT date, currency FROM transactions WHERE account_id=? AND amount != 0",
            (account_id,),
        ):
            to_base(c, 1, row["currency"], account["currency"], row["date"])


def reprice_user(c: sqlite3.Connection, user_id: int) -> int:
    """
    Recompute ``base_amount`` for every one of a user's transactions.

    Needed whenever the inputs to a conversion change underneath the stored
    result: a new reporting currency, a corrected rate, a backfilled feed.
    Returns how many rows moved.
    """
    base = base_currency(c, user_id)
    rows = c.execute(
        "SELECT t.id, t.date, t.amount, t.currency, t.base_amount FROM transactions t"
        " JOIN accounts a ON a.id = t.account_id WHERE a.user_id=?",
        (user_id,),
    ).fetchall()
    changed = 0
    for r in rows:
        value = to_base(c, r["amount"], r["currency"], base, r["date"])
        if value != r["base_amount"]:
            c.execute("UPDATE transactions SET base_amount=? WHERE id=?", (value, r["id"]))
            changed += 1
    return changed


def reprice_all(c: sqlite3.Connection) -> int:
    """
    Reprice every user's ledger.

    Rates are one shared table — what a currency was worth on a day is not a
    per-user fact — so a rate that moves moves everyone's totals, not just those
    of whoever pressed the button.
    """
    return sum(reprice_user(c, r["id"]) for r in c.execute("SELECT id FROM users"))


def reprice_plans(
    c: sqlite3.Connection,
    user_id: int,
    source_currency: str,
    target_currency: str,
    day: str,
) -> int:
    """Convert budget allocations and savings targets when reporting currency changes."""
    changed = 0
    budgets = c.execute(
        "SELECT b.rowid AS row_id, b.amount AS value FROM budgets b"
        " JOIN categories c ON c.id=b.category_id"
        " JOIN category_groups g ON g.id=c.group_id WHERE g.user_id=?",
        (user_id,),
    ).fetchall()
    for row in budgets:
        value = convert(c, row["value"], source_currency, target_currency, day)
        c.execute("UPDATE budgets SET amount=? WHERE rowid=?", (value, row["row_id"]))
        changed += 1
    goals = c.execute(
        "SELECT c.rowid AS row_id, c.goal_target AS value FROM categories c"
        " JOIN category_groups g ON g.id=c.group_id"
        " WHERE g.user_id=? AND c.goal_target IS NOT NULL",
        (user_id,),
    ).fetchall()
    for row in goals:
        value = convert(c, row["value"], source_currency, target_currency, day)
        c.execute("UPDATE categories SET goal_target=? WHERE rowid=?", (value, row["row_id"]))
        changed += 1
    return changed
