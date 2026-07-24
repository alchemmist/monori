"""
Accounts: every transaction gains a NOT NULL account_id and a nullable
transfer_id; pre-existing rows are backfilled onto a default 'T-Bank' account.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _has_column(conn, table, column):
    return any(r[1] == column for r in conn.exec_driver_sql(f"PRAGMA table_info({table})"))


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS accounts (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL UNIQUE,
      type TEXT NOT NULL DEFAULT 'other' CHECK (type IN ('card','cash','savings','other')),
      currency TEXT NOT NULL DEFAULT 'RUB',
      sort INTEGER NOT NULL DEFAULT 0,
      archived INTEGER NOT NULL DEFAULT 0,
      opening_balance INTEGER NOT NULL DEFAULT 0,
      opening_date TEXT
    )""")
    if not conn.exec_driver_sql("SELECT id FROM accounts LIMIT 1").fetchone():
        conn.exec_driver_sql(
            "INSERT INTO accounts (name, type, currency, sort) VALUES ('T-Bank', 'card', 'RUB', 1)"
        )
    default_id = conn.exec_driver_sql("SELECT MIN(id) FROM accounts").fetchone()[0]
    if not _has_column(conn, "transactions", "account_id"):
        conn.exec_driver_sql("""CREATE TABLE transactions_new (
          id INTEGER PRIMARY KEY,
          date TEXT NOT NULL,
          amount INTEGER NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          bank_category TEXT NOT NULL DEFAULT '',
          mcc TEXT NOT NULL DEFAULT '',
          category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
          account_id INTEGER NOT NULL REFERENCES accounts(id),
          transfer_id TEXT,
          comment TEXT NOT NULL DEFAULT '',
          hash TEXT NOT NULL,
          source TEXT NOT NULL DEFAULT 'import'
        )""")
        conn.exec_driver_sql(
            "INSERT INTO transactions_new "
            "(id, date, amount, description, bank_category, mcc, category_id, "
            " account_id, transfer_id, comment, hash, source) "
            "SELECT id, date, amount, description, bank_category, mcc, category_id, "
            f"       {int(default_id)}, NULL, comment, hash, source "
            "FROM transactions"
        )
        conn.exec_driver_sql("DROP TABLE transactions")
        conn.exec_driver_sql("ALTER TABLE transactions_new RENAME TO transactions")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions(hash)")
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id)"
        )
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id)")


def downgrade():
    raise NotImplementedError("monori migrations are forward-only")
