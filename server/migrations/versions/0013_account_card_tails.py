"""
Card tails on accounts, for routing imported bank CSVs.

A bank statement carries the masked card number (``*8181``); when an account
remembers its tail(s), the CSV import can pick the right account automatically
instead of making the user choose every time.
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE accounts ADD COLUMN card_tails TEXT NOT NULL DEFAULT ''")


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
