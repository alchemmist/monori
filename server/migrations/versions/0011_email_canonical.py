"""
Canonical email so one mailbox cannot own several accounts.

``users.email_canonical`` collapses a real inbox's aliases to a single key: a
``+tag`` suffix on the local part is dropped for every domain, and dots in the
local part are dropped for Gmail (which ignores them). A UNIQUE index enforces
one account per canonical address; existing rows are backfilled from their
stored email. The logic is inlined rather than imported from the app so this
migration stays a frozen snapshot, reproducible regardless of later app changes.
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}


def _canonical(email):
    email = email.strip().lower()
    local, sep, domain = email.partition("@")
    if not sep:
        return email
    base = local.split("+", 1)[0]
    if domain in GMAIL_DOMAINS:
        base = base.replace(".", "")
    return f"{base or local}@{domain}"


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN email_canonical TEXT NOT NULL DEFAULT ''")
    conn = op.get_bind()
    rows = conn.exec_driver_sql("SELECT id, email FROM users").fetchall()
    for uid, email in rows:
        conn.exec_driver_sql(
            "UPDATE users SET email_canonical = ? WHERE id = ?",
            (_canonical(email), uid),
        )
    op.execute("CREATE UNIQUE INDEX idx_users_email_canonical ON users (email_canonical)")


def downgrade():
    raise NotImplementedError("monori migrations are forward-only")
