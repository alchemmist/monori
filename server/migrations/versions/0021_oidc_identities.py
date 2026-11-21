# Copyright (c) 2026
"""Store external OIDC identities independently of email addresses."""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Associate each issuer and subject pair with one local user."""
    op.execute(
        "CREATE TABLE oidc_identities ( "
        "issuer TEXT NOT NULL, "
        "subject TEXT NOT NULL, "
        "user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE, "
        "PRIMARY KEY (issuer, subject) "
        ")"
    )


def downgrade() -> None:
    """Remove identity associations without deleting local users."""
    op.execute("DROP TABLE oidc_identities")
