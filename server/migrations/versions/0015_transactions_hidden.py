"""
A hidden flag on transactions (issue #193).

Deleting a transaction breaks bank sync — the connector sees it missing and
re-imports it. Hidden rows stay in the table so dedup still counts them, but
every read path (snapshot, lists, export, analytics) leaves them out.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE transactions ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")


def downgrade():
    raise NotImplementedError("forward-only migrations")
