"""
Automated import: bank connections, import batches, and a batch_id on
transactions pointing at the sync run that inserted the row.
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _has_column(conn, table, column):
    return any(r[1] == column for r in conn.exec_driver_sql(f"PRAGMA table_info({table})"))


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS bank_connections (
      id INTEGER PRIMARY KEY,
      account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      bank TEXT NOT NULL,
      kind TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'disconnected'
        CHECK (status IN ('disconnected','connected','awaiting_sms','error')),
      credentials_encrypted BLOB,
      session_encrypted BLOB,
      last_sync TEXT,
      last_error TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )""")
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_conn_account ON bank_connections(account_id)"
    )
    conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS import_batches (
      id INTEGER PRIMARY KEY,
      account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      connection_id INTEGER REFERENCES bank_connections(id) ON DELETE SET NULL,
      source TEXT NOT NULL,
      inserted INTEGER NOT NULL DEFAULT 0,
      skipped INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    )""")
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_batch_account ON import_batches(account_id)"
    )
    if not _has_column(conn, "transactions", "batch_id"):
        conn.exec_driver_sql(
            "ALTER TABLE transactions ADD COLUMN batch_id INTEGER"
            " REFERENCES import_batches(id) ON DELETE SET NULL"
        )


def downgrade():
    raise NotImplementedError("monori migrations are forward-only")
