"""Transfer Monori revision 0021 into an empty PostgreSQL database in one transaction.

Usage: DATABASE_URL (from secret) python scripts/import_postgres_0021.py /path/to/monori.db
The source is opened read-only. Use a cold source for the final switch.
"""

import hashlib
import os
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path

import psycopg
from psycopg import sql

from pg_ledger_receipt import receipt

SCHEMA = Path(__file__).resolve().parents[1] / "server/postgres/0021_oidc_identities.sql"


def fingerprints(rows):
    """Typed and length-delimited; no financial or identity data in logs."""
    result = Counter()
    for row in rows:
        digest = hashlib.sha256()
        for value in row:
            if value is None:
                tag, data = b"N", b""
            elif isinstance(value, bytes):
                tag, data = b"B", value
            elif isinstance(value, int):
                tag, data = b"I", str(value).encode()
            elif isinstance(value, str):
                tag, data = b"T", value.encode()
            else:
                raise ValueError("Unexpected stored type")
            digest.update(tag + len(data).to_bytes(8, "big") + data)
        result[digest.digest()] += 1
    return result


def transfer(src, dst):
    src.execute("BEGIN")
    if (
        src.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
        or src.execute("PRAGMA foreign_key_check").fetchone()
    ):
        raise ValueError("Invalid SQLite source")
    if src.execute("SELECT version_num FROM alembic_version").fetchall() != [("0021",)]:
        raise ValueError("Unsupported source revision")
    if dst.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' LIMIT 1"
    ).fetchone():
        raise ValueError("Destination is not empty")
    dst.execute(SCHEMA.read_text())
    dst.execute("SET CONSTRAINTS ALL DEFERRED")
    src_tables = {
        r[0]
        for r in src.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    dst_tables = {
        r[0]
        for r in dst.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )
    }
    if src_tables != dst_tables:
        raise ValueError("Schema tables differ")
    for table in sorted(dst_tables):
        columns = [r[1] for r in src.execute(f'PRAGMA table_info("{table}")')]
        pg_columns = dst.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
            (table,),
        ).fetchall()
        if set(columns) != {r[0] for r in pg_columns}:
            raise ValueError(f"Column mismatch: {table}")
        fields = sql.SQL(",").join(map(sql.Identifier, columns))
        rows = src.execute(f'SELECT * FROM "{table}"')
        with dst.cursor().copy(
            sql.SQL("COPY {} ({}) FROM STDIN").format(sql.Identifier(table), fields)
        ) as copy:
            for row in rows:
                copy.write_row(row)
        original = fingerprints(src.execute(f'SELECT * FROM "{table}"'))
        restored = fingerprints(
            dst.execute(sql.SQL("SELECT {} FROM {}").format(fields, sql.Identifier(table)))
        )
        if original != restored:
            raise ValueError(f"Content mismatch: {table}")
    dst.execute("SET CONSTRAINTS ALL IMMEDIATE")
    for table, col in dst.execute(
        "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND is_identity='YES'"
    ).fetchall():
        dst.execute(
            sql.SQL(
                "SELECT setval(pg_get_serial_sequence(%s,%s),COALESCE(MAX({c}),1),MAX({c}) IS NOT NULL) FROM {t}"
            ).format(c=sql.Identifier(col), t=sql.Identifier(table)),
            (table, col),
        )
    key = os.urandom(32)
    if receipt(src, key) != receipt(dst, key):
        raise ValueError("Financial ledger mismatch")
    print(f"Compared {len(dst_tables)} tables and all financial receipts.")


if __name__ == "__main__":
    with (
        closing(
            sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + "?mode=ro", uri=True)
        ) as source,
        psycopg.connect(os.environ["DATABASE_URL"]) as target,
    ):
        transfer(source, target)
