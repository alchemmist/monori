"""Accounts gain a display icon (a short glyph name mapped by the frontend)."""

from alembic import op
from sqlalchemy.engine import Connection

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _has_column(conn: Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.exec_driver_sql(f"PRAGMA table_info({table})"))


def upgrade() -> None:
    """Handle upgrade."""
    conn = op.get_bind()
    if not _has_column(conn, "accounts", "icon"):
        conn.exec_driver_sql("ALTER TABLE accounts ADD COLUMN icon TEXT NOT NULL DEFAULT 'wallet'")


def downgrade() -> None:
    """Handle downgrade."""
    msg = "monori migrations are forward-only"
    raise NotImplementedError(msg)
