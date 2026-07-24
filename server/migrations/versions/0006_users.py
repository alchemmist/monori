"""
First-class users that sign in to monori itself (issue #34). Passwords are
stored only as Argon2 hashes; per-user data ownership is a later phase.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL
    )""")


def downgrade():
    raise NotImplementedError("monori migrations are forward-only")
