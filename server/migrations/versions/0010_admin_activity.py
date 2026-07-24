"""
Admin flag and activity tracking.

``users`` gains ``is_admin`` (granted via the ``MONORI_ADMIN_EMAILS`` env, synced
at login) and ``last_login``. Two new tables back the admin panel's analytics:
``activity_events`` records logins, ``feature_usage`` keeps per-user per-feature
daily API counters.
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN last_login TEXT")
    op.execute(
        "CREATE TABLE activity_events ("
        " id INTEGER PRIMARY KEY,"
        " user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,"
        " kind TEXT NOT NULL,"
        " created_at TEXT NOT NULL)"
    )
    op.execute("CREATE INDEX idx_activity_user ON activity_events (user_id)")
    op.execute("CREATE INDEX idx_activity_created ON activity_events (created_at)")
    op.execute(
        "CREATE TABLE feature_usage ("
        " user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,"
        " feature TEXT NOT NULL,"
        " day TEXT NOT NULL,"
        " count INTEGER NOT NULL DEFAULT 0,"
        " PRIMARY KEY (user_id, feature, day))"
    )
    op.execute("CREATE INDEX idx_usage_day ON feature_usage (day)")


def downgrade():
    raise NotImplementedError("monori migrations are forward-only")
