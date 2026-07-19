"""Accounts gain a display icon (a short glyph name mapped by the frontend)."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _has_column(conn, table, column):
    return any(r[1] == column for r in conn.exec_driver_sql(f"PRAGMA table_info({table})"))


def upgrade():
    conn = op.get_bind()
    if not _has_column(conn, "accounts", "icon"):
        conn.exec_driver_sql("ALTER TABLE accounts ADD COLUMN icon TEXT NOT NULL DEFAULT 'wallet'")


def downgrade():
    raise NotImplementedError("monori migrations are forward-only")
