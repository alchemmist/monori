"""Links between refunds and their original purchases."""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """CREATE TABLE refund_links (
        refund_tx_id INTEGER PRIMARY KEY REFERENCES transactions (id) ON DELETE CASCADE,
        original_tx_id INTEGER NOT NULL REFERENCES transactions (id) ON DELETE CASCADE,
        CHECK (refund_tx_id <> original_tx_id)
        )"""
    )
    op.execute("CREATE INDEX idx_refund_links_original ON refund_links (original_tx_id)")


def downgrade():
    op.execute("DROP TABLE refund_links")
