"""First-class savings goals built on category envelopes."""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE category_group_types (
      id INTEGER PRIMARY KEY,
      type TEXT NOT NULL UNIQUE,
      transaction_sign INTEGER NOT NULL CHECK(transaction_sign IN (-1, 1)),
      is_goal INTEGER NOT NULL DEFAULT 0
    )""")
    op.execute(
        "INSERT INTO category_group_types(id, type, transaction_sign, is_goal)"
        " VALUES (1, 'income', 1, 0), (2, 'expense', -1, 0), (3, 'goal', -1, 1)",
    )

    op.execute("""CREATE TABLE category_groups_new (
      id INTEGER PRIMARY KEY,
      user_id INTEGER REFERENCES users(id),
      name TEXT NOT NULL,
      sort INTEGER NOT NULL,
      type_id INTEGER NOT NULL REFERENCES category_group_types(id),
      UNIQUE(user_id, name)
    )""")
    op.execute(
        "INSERT INTO category_groups_new (id, user_id, name, sort, type_id)"
        " SELECT g.id, g.user_id, g.name, g.sort, t.id FROM category_groups g"
        " JOIN category_group_types t ON t.type = g.kind",
    )
    op.execute("DROP TABLE category_groups")
    op.execute("ALTER TABLE category_groups_new RENAME TO category_groups")
    op.execute("CREATE INDEX IF NOT EXISTS idx_groups_user ON category_groups(user_id)")
    op.execute("ALTER TABLE categories ADD COLUMN goal_target INTEGER")
    op.execute(
        "ALTER TABLE categories ADD COLUMN goal_status TEXT"
        " CHECK (goal_status IN ('active', 'achieved', 'archived'))",
    )
    op.execute("ALTER TABLE categories ADD COLUMN goal_target_date TEXT")


def downgrade() -> None:
    msg = "forward-only migrations"
    raise NotImplementedError(msg)
