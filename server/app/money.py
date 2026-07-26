"""
The glue between a stored amount and what it is worth.

Three questions get asked all over the write paths — what currency is this
account held in, what currency does this user report in, and what is this
amount worth in that reporting currency on that day — and they are answered
here so every path answers them the same way.
"""

from .currencies import DEFAULT_CURRENCY, normalize
from .rates import RateUnavailable, convert


def account_currency(c, account_id):
    row = c.execute("SELECT currency FROM accounts WHERE id=?", (account_id,)).fetchone()
    return normalize(row["currency"] if row else None)


def base_currency(c, user_id):
    row = c.execute("SELECT base_currency FROM users WHERE id=?", (user_id,)).fetchone()
    return normalize(row["base_currency"] if row else None)


def base_currency_of_account(c, account_id):
    """
    The reporting currency of whoever owns this account. Ingestion knows the
    account it is writing to long before it knows the user.
    """
    row = c.execute(
        "SELECT u.base_currency FROM accounts a JOIN users u ON u.id = a.user_id WHERE a.id=?",
        (account_id,),
    ).fetchone()
    return normalize(row["base_currency"] if row else None)


def to_base(c, amount, currency, base, date):
    """
    ``amount`` in ``base``, at the rate for ``date``.

    A currency with no rate anywhere is carried across at face value rather
    than blocking the write: refusing to record a transaction because a rate
    feed was unreachable would be the worse failure, and the number is corrected
    the moment rates arrive (see :func:`reprice_user`).
    """
    try:
        return convert(c, amount, currency, base, date)
    except RateUnavailable:
        return amount


def resolve_currency(c, account_id, requested):
    """
    What a new transaction on this account is denominated in: what the caller
    asked for, else the account's own currency, else rubles.
    """
    code = normalize(requested, "")
    return code or account_currency(c, account_id) or DEFAULT_CURRENCY


def reprice_user(c, user_id):
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


def reprice_all(c):
    """
    Reprice every user's ledger.

    Rates are one shared table — what a currency was worth on a day is not a
    per-user fact — so a rate that moves moves everyone's totals, not just those
    of whoever pressed the button.
    """
    return sum(reprice_user(c, r["id"]) for r in c.execute("SELECT id FROM users"))
