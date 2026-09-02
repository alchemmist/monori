"""Make category names unique within a group."""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename pre-existing duplicates and add database enforcement."""
    connection = op.get_bind()
    rows = connection.exec_driver_sql(
        "SELECT id, group_id, name FROM categories ORDER BY group_id, id"
    ).fetchall()
    used: dict[int, set[str]] = {}
    for category_id, group_id, name in rows:
        names = used.setdefault(int(group_id), set())
        candidate = str(name)
        if candidate in names:
            suffix = 2
            while f"{candidate} ({suffix})" in names:
                suffix += 1
            candidate = f"{candidate} ({suffix})"
            connection.exec_driver_sql(
                "UPDATE categories SET name=? WHERE id=?",
                (candidate, int(category_id)),
            )
        names.add(candidate)
    op.execute("CREATE UNIQUE INDEX idx_categories_group_name ON categories (group_id, name)")


def downgrade() -> None:
    """Remove per-group category-name enforcement."""
    op.execute("DROP INDEX idx_categories_group_name")
