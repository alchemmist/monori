"""First-class savings goals built on category envelopes."""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE TABLE category_kinds (kind TEXT PRIMARY KEY)")
    op.execute("INSERT INTO category_kinds(kind) VALUES ('income'), ('expense'), ('goal')")
    # SQLite cannot alter the old CHECK in place. Rebuilding it also replaces
    # the closed enum with a lookup FK, so another kind won't require another
    # constraint rewrite.
    op.execute("""CREATE TABLE category_groups_new (
      id INTEGER PRIMARY KEY,
      user_id INTEGER REFERENCES users(id),
      name TEXT NOT NULL,
      sort INTEGER NOT NULL,
      kind TEXT NOT NULL REFERENCES category_kinds(kind),
      UNIQUE(user_id, name)
    )""")
    op.execute(
        "INSERT INTO category_groups_new (id, user_id, name, sort, kind)"
        " SELECT id, user_id, name, sort, kind FROM category_groups"
    )
    op.execute("DROP TABLE category_groups")
    op.execute("ALTER TABLE category_groups_new RENAME TO category_groups")
    op.execute("CREATE INDEX IF NOT EXISTS idx_groups_user ON category_groups(user_id)")
    op.execute("ALTER TABLE categories ADD COLUMN goal_target INTEGER")
    op.execute(
        "ALTER TABLE categories ADD COLUMN goal_status TEXT"
        " CHECK (goal_status IN ('active', 'achieved', 'archived'))"
    )
    op.execute("ALTER TABLE categories ADD COLUMN goal_target_date TEXT")


def downgrade():
    raise NotImplementedError("forward-only migrations")
