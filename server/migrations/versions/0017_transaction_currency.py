"""
Currency as a property of money, not of the app (issue #201).

Until now every amount was implicitly rubles: ``accounts.currency`` existed but
nothing read it, so a card in lari and a card in rubles were added together on
every total. Three things change that.

``transactions.currency`` records what the row is denominated in, stored rather
than looked up through the account, so re-denominating an account cannot rewrite
history. Existing rows inherit their account's currency, which is exactly what
they were.

``transactions.base_amount`` is the same money in the owner's reporting
currency, frozen at the rate for the transaction's date. It is the only column
aggregation may sum. All existing data is single-currency, so it backfills to
``amount``.

``exchange_rates`` holds rubles per unit per day — one pivot, so any pair of
currencies is two lookups — and ``users.base_currency`` says what to report in.

The dedup fingerprint gains the currency, so every existing row is rehashed in
place; leaving stale hashes behind would have the next sync treat the whole
ledger as new and duplicate it.
"""

import hashlib

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

CREATE_RATES = """
CREATE TABLE IF NOT EXISTS exchange_rates (
  day TEXT NOT NULL,
  code TEXT NOT NULL,
  rub_per_unit REAL NOT NULL,
  source TEXT NOT NULL DEFAULT 'cbr',
  PRIMARY KEY (day, code)
)
"""

# currency defaults to '' only so ALTER TABLE ADD COLUMN can backfill existing
# rows; a blank currency makes an amount meaningless, so nothing may write one
NOT_BLANK_INSERT = """
CREATE TRIGGER IF NOT EXISTS tx_currency_not_blank
BEFORE INSERT ON transactions WHEN new.currency = ''
BEGIN
SELECT RAISE(ABORT, 'transaction currency must not be blank');
END
"""

NOT_BLANK_UPDATE = """
CREATE TRIGGER IF NOT EXISTS tx_currency_not_blank_upd
BEFORE UPDATE ON transactions WHEN new.currency = ''
BEGIN
SELECT RAISE(ABORT, 'transaction currency must not be blank');
END
"""


BATCH = 1000


def _hash(account_id, date_iso, amount_kop, currency, description):
    return hashlib.sha256(
        f"{account_id}|{date_iso}|{amount_kop}|{currency}|{description}".encode()
    ).hexdigest()


def _rehash(conn):
    last_id = 0
    while True:
        rows = conn.exec_driver_sql(
            "SELECT id, account_id, date, amount, currency, description FROM transactions"
            " WHERE id > ? ORDER BY id LIMIT ?",
            (last_id, BATCH),
        ).fetchall()
        if not rows:
            break
        for tid, account_id, date, amount, currency, description in rows:
            conn.exec_driver_sql(
                "UPDATE transactions SET hash=? WHERE id=?",
                (_hash(account_id, date, amount, currency, description or ""), tid),
            )
        last_id = rows[-1][0]


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN base_currency TEXT NOT NULL DEFAULT 'RUB'")
    op.execute("ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE transactions ADD COLUMN base_amount INTEGER NOT NULL DEFAULT 0")
    op.execute(
        "UPDATE transactions SET currency = COALESCE("
        "  NULLIF((SELECT a.currency FROM accounts a WHERE a.id = transactions.account_id), ''),"
        "  'RUB'), base_amount = amount"
    )
    op.execute(CREATE_RATES)
    op.execute("CREATE INDEX IF NOT EXISTS idx_rates_code ON exchange_rates (code, day)")
    op.execute(NOT_BLANK_INSERT)
    op.execute(NOT_BLANK_UPDATE)
    _rehash(op.get_bind())


def downgrade():
    raise NotImplementedError("forward-only migrations")
