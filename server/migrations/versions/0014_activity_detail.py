"""
A free-form detail on activity events, for the admin SQL console (issue #168).

Login events carry all their meaning in ``kind``; an executed statement does
not — the audit trail is worthless without the statement text itself.
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Handle upgrade."""
    op.execute("ALTER TABLE activity_events ADD COLUMN detail TEXT")


def downgrade() -> None:
    """Handle downgrade."""
    msg = "forward-only migrations"
    raise NotImplementedError(msg)
