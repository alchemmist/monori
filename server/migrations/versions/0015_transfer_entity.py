"""Transfers as a first-class entity, plus the rejections that mute auto-detection.

Until now a transfer was only a shared ``transactions.transfer_id``: nothing
stopped a third row joining the group or a row belonging to two transfers at
once, and there was nowhere to record where the link came from or what the legs
were categorized as before merging. The new ``transfers`` table owns all of
that; ``transfer_id`` stays as the denormalized pointer the snapshot serves.

Existing pairs are backfilled as ``origin='manual'`` — they can only have come
from the transfer dialog. Any malformed group (not exactly one outflow and one
inflow) keeps its ``transfer_id`` but gets no row here, so nothing is lost.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

CREATE_TRANSFERS = """
CREATE TABLE IF NOT EXISTS transfers (
  id TEXT PRIMARY KEY,
  user_id INTEGER REFERENCES users (id),
  out_tx_id INTEGER NOT NULL UNIQUE REFERENCES transactions (id) ON DELETE CASCADE,
  in_tx_id INTEGER NOT NULL UNIQUE REFERENCES transactions (id) ON DELETE CASCADE,
  origin TEXT NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual', 'matched')),
  out_category_id INTEGER,
  in_category_id INTEGER,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
)
"""

CREATE_REJECTIONS = """
CREATE TABLE IF NOT EXISTS transfer_rejections (
  out_tx_id INTEGER NOT NULL REFERENCES transactions (id) ON DELETE CASCADE,
  in_tx_id INTEGER NOT NULL REFERENCES transactions (id) ON DELETE CASCADE,
  PRIMARY KEY (out_tx_id, in_tx_id)
)
"""

BACKFILL = """
INSERT INTO transfers (id, user_id, out_tx_id, in_tx_id, origin,
                       out_category_id, in_category_id, note, created_at)
SELECT t.transfer_id,
       MIN(a.user_id),
       MIN(CASE WHEN t.amount < 0 THEN t.id END),
       MIN(CASE WHEN t.amount > 0 THEN t.id END),
       'manual',
       MIN(CASE WHEN t.amount < 0 THEN t.category_id END),
       MIN(CASE WHEN t.amount > 0 THEN t.category_id END),
       MIN(t.comment),
       MIN(t.date)
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE t.transfer_id IS NOT NULL
GROUP BY t.transfer_id
HAVING COUNT(*) = 2
   AND SUM(CASE WHEN t.amount < 0 THEN 1 ELSE 0 END) = 1
   AND SUM(CASE WHEN t.amount > 0 THEN 1 ELSE 0 END) = 1
"""


def upgrade() -> None:
    """Handle upgrade."""
    op.execute(CREATE_TRANSFERS)
    op.execute("CREATE INDEX IF NOT EXISTS idx_transfers_user ON transfers (user_id)")
    op.execute(CREATE_REJECTIONS)
    op.execute(BACKFILL)


def downgrade() -> None:
    """Handle downgrade."""
    msg = "forward-only migrations"
    raise NotImplementedError(msg)
