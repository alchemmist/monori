"""A per-user default account for rows no card number can route: statement.

imports and workbook migrations preselect it instead of asking every time.
Empty keeps the current behavior — the user assigns those rows by hand.
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Handle upgrade."""
    op.execute("ALTER TABLE users ADD COLUMN default_account_id INTEGER REFERENCES accounts (id)")


def downgrade() -> None:
    """Handle downgrade."""
    msg = "forward-only migrations"
    raise NotImplementedError(msg)
