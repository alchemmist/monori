"""SQLite access layer. All money amounts are stored as integer kopecks."""

import os
import pathlib
import sqlite3

DB_PATH = os.environ.get(
    "MONORI_DB", str(pathlib.Path(__file__).resolve().parent.parent / "data" / "monori.db")
)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS category_groups (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  sort INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('income', 'expense'))
);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES category_groups(id),
  name TEXT NOT NULL UNIQUE,
  keywords TEXT NOT NULL DEFAULT '',
  sort INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,                -- ISO-8601 datetime
  amount INTEGER NOT NULL,           -- signed kopecks; negative = expense
  description TEXT NOT NULL DEFAULT '',
  bank_category TEXT NOT NULL DEFAULT '',
  mcc TEXT NOT NULL DEFAULT '',
  category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  comment TEXT NOT NULL DEFAULT '',
  hash TEXT NOT NULL,                -- sha1(date|amount|description) for dedup
  source TEXT NOT NULL DEFAULT 'import'
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions(hash);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);

CREATE TABLE IF NOT EXISTS budgets (
  category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
  amount INTEGER NOT NULL,           -- kopecks
  PRIMARY KEY (category_id, year, month)
);
"""


def _has_column(conn, table, column):
    return any(r["name"] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def _migrate_accounts(conn):
    """Introduce the accounts system: every transaction gains a NOT NULL
    account_id and a nullable transfer_id linking the two rows of a transfer.
    All pre-existing rows are backfilled onto a default 'T-Bank' account so
    current data behaves exactly as before."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS accounts (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL UNIQUE,
      type TEXT NOT NULL DEFAULT 'other' CHECK (type IN ('card','cash','savings','other')),
      currency TEXT NOT NULL DEFAULT 'RUB',
      sort INTEGER NOT NULL DEFAULT 0,
      archived INTEGER NOT NULL DEFAULT 0,
      opening_balance INTEGER NOT NULL DEFAULT 0,   -- kopecks
      opening_date TEXT
    );
    """)
    if not conn.execute("SELECT id FROM accounts LIMIT 1").fetchone():
        conn.execute(
            "INSERT INTO accounts (name, type, currency, sort) VALUES ('T-Bank', 'card', 'RUB', 1)"
        )
    default_id = conn.execute("SELECT MIN(id) FROM accounts").fetchone()[0]
    if not _has_column(conn, "transactions", "account_id"):
        conn.executescript("""
        CREATE TABLE transactions_new (
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
        );
        """)
        conn.execute(
            """INSERT INTO transactions_new
               (id, date, amount, description, bank_category, mcc, category_id,
                account_id, transfer_id, comment, hash, source)
               SELECT id, date, amount, description, bank_category, mcc, category_id,
                      ?, NULL, comment, hash, source
               FROM transactions""",
            (default_id,),
        )
        conn.executescript("""
        DROP TABLE transactions;
        ALTER TABLE transactions_new RENAME TO transactions;
        CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
        CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions(hash);
        CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);
        CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id);
        """)


MIGRATIONS = [_migrate_accounts]


def _run_migrations(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for step in MIGRATIONS[version:]:
        step(conn)
    if len(MIGRATIONS) != version:
        conn.execute(f"PRAGMA user_version = {len(MIGRATIONS)}")
        conn.commit()


def connect(db_path=None):
    path = pathlib.Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _run_migrations(conn)
    return conn
