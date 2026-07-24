"""
Recompute every transaction's dedup fingerprint with SHA-256.

The fingerprint (``transactions.hash``) switched from SHA-1 to SHA-256. Dedup
compares freshly computed hashes against the stored ones, so existing rows must
be rehashed in place or the next import/sync would treat every prior row as new
and duplicate it.
"""

import hashlib

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

BATCH = 1000


def _hash(date_iso, amount_kop, description):
    return hashlib.sha256(f"{date_iso}|{amount_kop}|{description}".encode()).hexdigest()


def upgrade():
    conn = op.get_bind()
    last_id = 0
    while True:
        rows = conn.exec_driver_sql(
            "SELECT id, date, amount, description FROM transactions"
            " WHERE id > ? ORDER BY id LIMIT ?",
            (last_id, BATCH),
        ).fetchall()
        if not rows:
            break
        for tid, date, amount, description in rows:
            conn.exec_driver_sql(
                "UPDATE transactions SET hash=? WHERE id=?",
                (_hash(date, amount, description or ""), tid),
            )
        last_id = rows[-1][0]


def downgrade():
    raise NotImplementedError("SHA-1 fingerprints are not restorable")
