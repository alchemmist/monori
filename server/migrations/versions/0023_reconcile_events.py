# Copyright (c) 2026
"""Keep account reconciliation history, including exact matches."""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Record future reconciliations without inventing historical balances."""
    op.execute("""
CREATE TABLE reconcile_events (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    actual_balance INTEGER NOT NULL,
    computed_balance INTEGER NOT NULL,
    delta INTEGER NOT NULL CHECK (delta = actual_balance - computed_balance),
    adjustment_tx_id INTEGER REFERENCES transactions (id) ON DELETE SET NULL
)
""")
    op.execute(
        "CREATE INDEX idx_reconcile_events_account ON reconcile_events (account_id, id DESC)"
    )


def downgrade() -> None:
    """Remove the history table, leaving adjustments untouched."""
    op.execute("DROP TABLE reconcile_events")
