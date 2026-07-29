"""Categorized splits of a bank transaction."""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """CREATE TABLE splits (
        id INTEGER PRIMARY KEY,
        transaction_id INTEGER NOT NULL REFERENCES transactions (id) ON DELETE CASCADE,
        category_id INTEGER NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,
        amount INTEGER NOT NULL,
        comment TEXT NOT NULL DEFAULT '',
        sort INTEGER NOT NULL DEFAULT 0,
        UNIQUE (transaction_id, sort)
        )"""
    )
    op.execute("CREATE INDEX idx_splits_transaction ON splits (transaction_id)")
    op.execute("CREATE INDEX idx_splits_category ON splits (category_id)")


def downgrade():
    op.execute("DROP TABLE splits")
