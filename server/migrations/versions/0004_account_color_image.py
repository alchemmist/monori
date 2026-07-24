"""
Accounts gain a display color and an optional custom icon image.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _has_column(conn, table, column):
    return any(r[1] == column for r in conn.exec_driver_sql(f"PRAGMA table_info({table})"))


def upgrade():
    conn = op.get_bind()
    if not _has_column(conn, "accounts", "color"):
        conn.exec_driver_sql(
            "ALTER TABLE accounts ADD COLUMN color TEXT NOT NULL DEFAULT '#5b6472'"
        )
    if not _has_column(conn, "accounts", "icon_image"):
        conn.exec_driver_sql("ALTER TABLE accounts ADD COLUMN icon_image TEXT")


def downgrade():
    raise NotImplementedError("monori migrations are forward-only")
