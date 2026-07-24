-- Canonical monori schema: the full, current shape of the database.
-- Fresh databases are created from this file and stamped at the latest
-- alembic revision; existing databases reach the same shape by running
-- the migration chain in server/migrations/versions/.
-- All money amounts are integer kopecks.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS category_groups (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users (id),
  name TEXT NOT NULL,
  sort INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
  UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_groups_user ON category_groups (user_id);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES category_groups (id),
  name TEXT NOT NULL,
  keywords TEXT NOT NULL DEFAULT '',
  sort INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_categories_group ON categories (group_id);

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users (id),
  name TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'other' CHECK (type IN ('card', 'cash', 'savings', 'other')),
  currency TEXT NOT NULL DEFAULT 'RUB',
  sort INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  opening_balance INTEGER NOT NULL DEFAULT 0,   -- kopecks
  opening_date TEXT,
  icon TEXT NOT NULL DEFAULT 'wallet',
  color TEXT NOT NULL DEFAULT '#5b6472',
  icon_image TEXT,
  connection_id INTEGER REFERENCES bank_connections (id),
  bank_ref TEXT NOT NULL DEFAULT '',
  UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts (user_id);
CREATE INDEX IF NOT EXISTS idx_accounts_connection ON accounts (connection_id);

CREATE TABLE IF NOT EXISTS bank_connections (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users (id),
  bank TEXT NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'disconnected'
  CHECK (status IN ('disconnected', 'connected', 'awaiting_sms', 'error')),
  credentials_encrypted BLOB,
  session_encrypted BLOB,
  last_sync TEXT,
  last_error TEXT,
  pending_account_id INTEGER REFERENCES accounts (id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conn_user ON bank_connections (user_id);

CREATE TABLE IF NOT EXISTS import_batches (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
  connection_id INTEGER REFERENCES bank_connections (id) ON DELETE SET NULL,
  source TEXT NOT NULL,
  inserted INTEGER NOT NULL DEFAULT 0,
  skipped INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_batch_account ON import_batches (account_id);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,                -- ISO-8601 datetime
  amount INTEGER NOT NULL,           -- signed kopecks; negative = expense
  description TEXT NOT NULL DEFAULT '',
  bank_category TEXT NOT NULL DEFAULT '',
  mcc TEXT NOT NULL DEFAULT '',
  category_id INTEGER REFERENCES categories (id) ON DELETE SET NULL,
  account_id INTEGER NOT NULL REFERENCES accounts (id),
  transfer_id TEXT,                  -- links the two rows of a transfer
  comment TEXT NOT NULL DEFAULT '',
  hash TEXT NOT NULL,                -- sha1(date|amount|description) for dedup
  source TEXT NOT NULL DEFAULT 'import',
  batch_id INTEGER REFERENCES import_batches (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions (date);
CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions (hash);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions (category_id);
CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions (account_id);

CREATE TABLE IF NOT EXISTS budgets (
  category_id INTEGER NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
  amount INTEGER NOT NULL,           -- kopecks
  PRIMARY KEY (category_id, year, month)
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  email_canonical TEXT NOT NULL DEFAULT '',   -- aliasing-collapsed key, one per mailbox
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  is_admin INTEGER NOT NULL DEFAULT 0,
  last_login TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_canonical ON users (email_canonical);

CREATE TABLE IF NOT EXISTS activity_events (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_events (user_id);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_events (created_at);

CREATE TABLE IF NOT EXISTS feature_usage (
  user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  feature TEXT NOT NULL,
  day TEXT NOT NULL,                 -- ISO date, UTC
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, feature, day)
);
CREATE INDEX IF NOT EXISTS idx_usage_day ON feature_usage (day);
