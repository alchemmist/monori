-- Canonical monori schema: the full, current shape of the database.
-- Fresh databases are created from this file and stamped at the latest
-- alembic revision; existing databases reach the same shape by running
-- the migration chain in server/migrations/versions/.
-- All money amounts are integer kopecks.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS category_group_types (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL UNIQUE,
  transaction_sign INTEGER NOT NULL CHECK (transaction_sign IN (-1, 1)),
  is_goal INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO category_group_types (id, type, transaction_sign, is_goal) VALUES
(1, 'income', 1, 0),
(2, 'expense', -1, 0),
(3, 'goal', -1, 1);

CREATE TABLE IF NOT EXISTS category_groups (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users (id),
  name TEXT NOT NULL,
  sort INTEGER NOT NULL,
  type_id INTEGER NOT NULL REFERENCES category_group_types (id),
  UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_groups_user ON category_groups (user_id);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES category_groups (id),
  name TEXT NOT NULL,
  keywords TEXT NOT NULL DEFAULT '',
  sort INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  goal_target INTEGER,
  goal_status TEXT CHECK (goal_status IN ('active', 'achieved', 'archived')),
  goal_target_date TEXT
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
  card_tails TEXT NOT NULL DEFAULT '', -- comma-separated card tails, e.g. '8181,2947'
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
  hash TEXT NOT NULL,                -- sha256(account_id|date|amount|description) for dedup
  source TEXT NOT NULL DEFAULT 'import',
  batch_id INTEGER REFERENCES import_batches (id) ON DELETE SET NULL,
  hidden INTEGER NOT NULL DEFAULT 0 -- excluded everywhere but kept for sync dedup
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions (date);
CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions (hash);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions (category_id);
CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions (account_id);

CREATE TABLE IF NOT EXISTS recurring_transactions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  account_id INTEGER NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
  category_id INTEGER REFERENCES categories (id) ON DELETE SET NULL,
  description TEXT NOT NULL DEFAULT '',
  amount INTEGER NOT NULL,
  frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly', 'yearly')),
  interval INTEGER NOT NULL DEFAULT 1 CHECK (interval > 0),
  start_date TEXT NOT NULL,
  next_date TEXT NOT NULL,
  end_date TEXT,
  auto_create INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recurring_user ON recurring_transactions (user_id);

CREATE TABLE IF NOT EXISTS recurring_occurrences (
  recurring_id INTEGER NOT NULL REFERENCES recurring_transactions (id) ON DELETE CASCADE,
  due_date TEXT NOT NULL,
  transaction_id INTEGER REFERENCES transactions (id) ON DELETE SET NULL,
  PRIMARY KEY (recurring_id, due_date)
);

CREATE TABLE IF NOT EXISTS splits (
  id INTEGER PRIMARY KEY,
  transaction_id INTEGER NOT NULL REFERENCES transactions (id) ON DELETE CASCADE,
  category_id INTEGER NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,
  amount INTEGER NOT NULL,
  comment TEXT NOT NULL DEFAULT '',
  sort INTEGER NOT NULL DEFAULT 0,
  UNIQUE (transaction_id, sort)
);
CREATE INDEX IF NOT EXISTS idx_splits_transaction ON splits (transaction_id);
CREATE INDEX IF NOT EXISTS idx_splits_category ON splits (category_id);

-- A transfer is the entity two transactions are merged into; the rows themselves
-- stay untouched so a re-sync still recognizes them and cannot duplicate them.
-- UNIQUE on both legs is what guarantees a transfer has exactly two of them and
-- that a transaction belongs to at most one transfer.
CREATE TABLE IF NOT EXISTS transfers (
  id TEXT PRIMARY KEY,
  user_id INTEGER REFERENCES users (id),
  out_tx_id INTEGER NOT NULL UNIQUE REFERENCES transactions (id) ON DELETE CASCADE,
  in_tx_id INTEGER NOT NULL UNIQUE REFERENCES transactions (id) ON DELETE CASCADE,
  origin TEXT NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual', 'matched')),
  out_category_id INTEGER,           -- categories the legs carried before merging,
  in_category_id INTEGER,            -- restored when the transfer is split again
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transfers_user ON transfers (user_id);

-- pairs the user rejected, so auto-detection stops offering them forever
CREATE TABLE IF NOT EXISTS transfer_rejections (
  out_tx_id INTEGER NOT NULL REFERENCES transactions (id) ON DELETE CASCADE,
  in_tx_id INTEGER NOT NULL REFERENCES transactions (id) ON DELETE CASCADE,
  PRIMARY KEY (out_tx_id, in_tx_id)
);

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
  last_login TEXT,
  -- where an import lands rows whose account cannot be told from the file
  -- (no card number anywhere); empty means the user assigns them by hand
  default_account_id INTEGER REFERENCES accounts (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_canonical ON users (email_canonical);

-- email_canonical defaults to '' only so ALTER TABLE ADD COLUMN can backfill
-- legacy rows; a blank value can never authenticate (login resolves by it) and
-- would collide on the unique index, so reject any insert or update that blanks it
CREATE TRIGGER IF NOT EXISTS users_email_canonical_not_blank
BEFORE INSERT ON users WHEN new.email_canonical = ''
BEGIN
SELECT RAISE(ABORT, 'email_canonical must not be blank');
END;

CREATE TRIGGER IF NOT EXISTS users_email_canonical_not_blank_upd
BEFORE UPDATE ON users WHEN new.email_canonical = ''
BEGIN
SELECT RAISE(ABORT, 'email_canonical must not be blank');
END;

CREATE TABLE IF NOT EXISTS activity_events (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  created_at TEXT NOT NULL,
  detail TEXT                        -- free-form payload, e.g. the SQL executed
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
