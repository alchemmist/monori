"""Bank connections become user-level: a connection is one bank login owned by
a user, and any number of accounts link to it via accounts.connection_id plus a
bank-specific accounts.bank_ref locator. Existing 1:1 connections are converted
in place; the legacy account id kept inside encrypted credentials remains a
fallback the connector still honors."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _has_column(conn, table, column):
    return any(r[1] == column for r in conn.exec_driver_sql(f"PRAGMA table_info({table})"))


def upgrade():
    conn = op.get_bind()
    if not _has_column(conn, "accounts", "connection_id"):
        conn.exec_driver_sql(
            "ALTER TABLE accounts ADD COLUMN connection_id INTEGER REFERENCES bank_connections(id)"
        )
        conn.exec_driver_sql("ALTER TABLE accounts ADD COLUMN bank_ref TEXT NOT NULL DEFAULT ''")
    if not _has_column(conn, "bank_connections", "user_id"):
        conn.exec_driver_sql(
            "UPDATE accounts SET connection_id ="
            " (SELECT bc.id FROM bank_connections bc WHERE bc.account_id = accounts.id"
            "  ORDER BY bc.id LIMIT 1)"
        )
        conn.exec_driver_sql("""CREATE TABLE bank_connections_new (
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
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )""")
        conn.exec_driver_sql(
            "INSERT INTO bank_connections_new (id, user_id, bank, kind, status,"
            " credentials_encrypted, session_encrypted, last_sync, last_error,"
            " created_at, updated_at)"
            " SELECT bc.id, a.user_id, bc.bank, bc.kind, bc.status,"
            " bc.credentials_encrypted, bc.session_encrypted, bc.last_sync, bc.last_error,"
            " bc.created_at, bc.updated_at"
            " FROM bank_connections bc LEFT JOIN accounts a ON a.id = bc.account_id"
        )
        conn.exec_driver_sql("DROP TABLE bank_connections")
        conn.exec_driver_sql("ALTER TABLE bank_connections_new RENAME TO bank_connections")
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_conn_user ON bank_connections(user_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_accounts_connection ON accounts(connection_id)"
        )


def downgrade():
    raise NotImplementedError("monori migrations are forward-only")
