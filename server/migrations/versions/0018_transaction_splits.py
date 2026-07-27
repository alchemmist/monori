"""Categorized parts of a bank transaction."""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """CREATE TABLE transaction_splits (
        id INTEGER PRIMARY KEY,
        transaction_id INTEGER NOT NULL REFERENCES transactions (id) ON DELETE CASCADE,
        category_id INTEGER NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,
        amount INTEGER NOT NULL,
        comment TEXT NOT NULL DEFAULT '',
        sort INTEGER NOT NULL DEFAULT 0,
        UNIQUE (transaction_id, sort)
        )"""
    )
    op.execute("CREATE INDEX idx_splits_transaction ON transaction_splits (transaction_id)")
    op.execute("CREATE INDEX idx_splits_category ON transaction_splits (category_id)")


def downgrade():
    op.execute("DROP TABLE transaction_splits")
