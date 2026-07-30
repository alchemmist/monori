"""Recurring transaction templates and generated occurrences."""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """CREATE TABLE recurring_transactions (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        account_id INTEGER NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
        category_id INTEGER REFERENCES categories (id) ON DELETE SET NULL,
        description TEXT NOT NULL DEFAULT '',
        amount INTEGER NOT NULL,
        frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly', 'yearly')),
        interval INTEGER NOT NULL DEFAULT 1 CHECK (interval > 0),
        start_date TEXT NOT NULL,
        next_date TEXT NOT NULL,
        end_date TEXT,
        auto_create INTEGER NOT NULL DEFAULT 1,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
        )"""
    )
    op.execute("CREATE INDEX idx_recurring_user ON recurring_transactions (user_id)")
    op.execute(
        """CREATE TABLE recurring_occurrences (
        recurring_id INTEGER NOT NULL REFERENCES recurring_transactions (id) ON DELETE CASCADE,
        due_date TEXT NOT NULL,
        transaction_id INTEGER REFERENCES transactions (id) ON DELETE SET NULL,
        PRIMARY KEY (recurring_id, due_date)
        )"""
    )


def downgrade():
    raise NotImplementedError("forward-only migrations")
