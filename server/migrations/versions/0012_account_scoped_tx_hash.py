"""
Recompute every transaction's dedup fingerprint with the account included.

``transactions.hash`` used to cover only date|amount|description, so the same
operation on two different accounts (transfer legs, mirrored cards) collided
and bank syncs dropped genuinely distinct rows as duplicates. The fingerprint
now starts with the account id; existing rows must be rehashed in place or the
next import/sync would treat every prior row as new and duplicate it.
"""

import hashlib

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

BATCH = 1000


def _hash(
    account_id: int, date_iso: str, amount_kop: int, description: str
) -> str:
    return hashlib.sha256(
        f"{account_id}|{date_iso}|{amount_kop}|{description}".encode()
    ).hexdigest()


def upgrade() -> None:
    conn = op.get_bind()
    last_id = 0
    while True:
        rows = conn.exec_driver_sql(
            "SELECT id, account_id, date, amount, description FROM transactions"
            " WHERE id > ? ORDER BY id LIMIT ?",
            (last_id, BATCH),
        ).fetchall()
        if not rows:
            break
        for tid, account_id, date, amount, description in rows:
            conn.exec_driver_sql(
                "UPDATE transactions SET hash=? WHERE id=?",
                (_hash(account_id, date, amount, description or ""), tid),
            )
        last_id = rows[-1][0]


def downgrade() -> None:
    raise NotImplementedError("account-less fingerprints are not restorable")
