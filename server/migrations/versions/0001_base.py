"""
Base schema: category groups, categories, transactions, budgets.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS category_groups (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL UNIQUE,
      sort INTEGER NOT NULL,
      kind TEXT NOT NULL CHECK (kind IN ('income', 'expense'))
    )""",
    """CREATE TABLE IF NOT EXISTS categories (
      id INTEGER PRIMARY KEY,
      group_id INTEGER NOT NULL REFERENCES category_groups(id),
      name TEXT NOT NULL UNIQUE,
      keywords TEXT NOT NULL DEFAULT '',
      sort INTEGER NOT NULL DEFAULT 0,
      archived INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS transactions (
      id INTEGER PRIMARY KEY,
      date TEXT NOT NULL,
      amount INTEGER NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      bank_category TEXT NOT NULL DEFAULT '',
      mcc TEXT NOT NULL DEFAULT '',
      category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
      comment TEXT NOT NULL DEFAULT '',
      hash TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'import'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date)",
    "CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions(hash)",
    "CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id)",
    """CREATE TABLE IF NOT EXISTS budgets (
      category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
      year INTEGER NOT NULL,
      month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
      amount INTEGER NOT NULL,
      PRIMARY KEY (category_id, year, month)
    )""",
]


def upgrade():
    conn = op.get_bind()
    for statement in STATEMENTS:
        conn.exec_driver_sql(statement)


def downgrade():
    raise NotImplementedError("monori migrations are forward-only")
