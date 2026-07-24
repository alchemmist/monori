"""
Multi-tenancy: accounts and category groups gain an owning user_id, and name
uniqueness becomes per-user. Categories lose their global unique name (they are
scoped through their group's owner). Rows predating registration keep a NULL
user_id and are claimed by the first user who registers.
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _has_column(conn, table, column):
    return any(r[1] == column for r in conn.exec_driver_sql(f"PRAGMA table_info({table})"))


def upgrade():
    conn = op.get_bind()
    if not _has_column(conn, "accounts", "user_id"):
        conn.exec_driver_sql("""CREATE TABLE accounts_new (
          id INTEGER PRIMARY KEY,
          user_id INTEGER REFERENCES users(id),
          name TEXT NOT NULL,
          type TEXT NOT NULL DEFAULT 'other' CHECK (type IN ('card','cash','savings','other')),
          currency TEXT NOT NULL DEFAULT 'RUB',
          sort INTEGER NOT NULL DEFAULT 0,
          archived INTEGER NOT NULL DEFAULT 0,
          opening_balance INTEGER NOT NULL DEFAULT 0,
          opening_date TEXT,
          icon TEXT NOT NULL DEFAULT 'wallet',
          color TEXT NOT NULL DEFAULT '#5b6472',
          icon_image TEXT,
          UNIQUE (user_id, name)
        )""")
        conn.exec_driver_sql(
            "INSERT INTO accounts_new (id, user_id, name, type, currency, sort, archived,"
            " opening_balance, opening_date, icon, color, icon_image)"
            " SELECT id, NULL, name, type, currency, sort, archived,"
            " opening_balance, opening_date, icon, color, icon_image FROM accounts"
        )
        conn.exec_driver_sql("DROP TABLE accounts")
        conn.exec_driver_sql("ALTER TABLE accounts_new RENAME TO accounts")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id)")
    if not _has_column(conn, "category_groups", "user_id"):
        conn.exec_driver_sql("""CREATE TABLE category_groups_new (
          id INTEGER PRIMARY KEY,
          user_id INTEGER REFERENCES users(id),
          name TEXT NOT NULL,
          sort INTEGER NOT NULL,
          kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
          UNIQUE (user_id, name)
        )""")
        conn.exec_driver_sql(
            "INSERT INTO category_groups_new (id, user_id, name, sort, kind)"
            " SELECT id, NULL, name, sort, kind FROM category_groups"
        )
        conn.exec_driver_sql("DROP TABLE category_groups")
        conn.exec_driver_sql("ALTER TABLE category_groups_new RENAME TO category_groups")
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_groups_user ON category_groups(user_id)"
        )
    unique_cat_name = any(
        "sqlite_autoindex" in (r[1] or "")
        for r in conn.exec_driver_sql("PRAGMA index_list(categories)")
    )
    if unique_cat_name:
        conn.exec_driver_sql("""CREATE TABLE categories_new (
          id INTEGER PRIMARY KEY,
          group_id INTEGER NOT NULL REFERENCES category_groups(id),
          name TEXT NOT NULL,
          keywords TEXT NOT NULL DEFAULT '',
          sort INTEGER NOT NULL DEFAULT 0,
          archived INTEGER NOT NULL DEFAULT 0
        )""")
        conn.exec_driver_sql(
            "INSERT INTO categories_new (id, group_id, name, keywords, sort, archived)"
            " SELECT id, group_id, name, keywords, sort, archived FROM categories"
        )
        conn.exec_driver_sql("DROP TABLE categories")
        conn.exec_driver_sql("ALTER TABLE categories_new RENAME TO categories")
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_categories_group ON categories(group_id)"
        )
    for table in ("accounts", "category_groups"):
        conn.exec_driver_sql(
            f"UPDATE {table} SET user_id=(SELECT MIN(id) FROM users)"
            " WHERE user_id IS NULL AND EXISTS (SELECT 1 FROM users)"
        )


def downgrade():
    raise NotImplementedError("monori migrations are forward-only")
