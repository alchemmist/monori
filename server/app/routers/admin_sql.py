"""
Admin SQL console (issue #168): run one statement against the live database.

This is deliberately unrestricted full data access — the same scope the rest of
the admin API already has (#128), for an instance owner who would otherwise SSH
in and open the file with the sqlite3 CLI. What the endpoint does add over that
CLI is safety rails: one statement at a time, everything inside an explicit
transaction, writes refused unless the caller confirmed them, reads capped, a
wall-clock ceiling on runaway queries, and an audit row per attempt.
"""

import contextlib
import sqlite3
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..admin import admin_user
from ..deps import conn

router = APIRouter(prefix="/api/admin", tags=["admin"])

ROW_LIMIT = 1000
STATEMENT_MAX_CHARS = 20000
AUDIT_MAX_CHARS = 4000
QUERY_TIMEOUT_S = 15.0
# SQLite calls the progress handler every N virtual-machine instructions; small
# enough to notice the deadline promptly, large enough not to dominate the query
PROGRESS_INSTRUCTIONS = 10000
BLOB_PREVIEW = 32
# ROW_LIMIT alone does not bound the response: one row can hold a megabyte of
# TEXT. The console is for reading data, not for exporting it — a cell longer
# than this comes back cut, with the dropped length spelled out
CELL_MAX_CHARS = 4096


def leading_keyword(sql):
    """
    The first word of a statement, past any leading whitespace and comments —
    ``UPDATE`` in ``/* fix */ -- one row\\n update users …``. Used only to name
    the statement back to the admin; classification never relies on it.

    Scanned character by character rather than with a regex on purpose: an
    alternation of whitespace and comment forms backtracks polynomially on
    adversarial input like ``/*/*/*…``, and the statement comes from a request.
    """
    i, n = 0, len(sql)
    while i < n:
        if sql[i].isspace():
            i += 1
        elif sql.startswith("--", i):
            end = sql.find("\n", i)
            if end < 0:
                return ""
            i = end + 1
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            if end < 0:
                return ""
            i = end + 2
        else:
            return sql[i:].split(None, 1)[0].upper()
    return ""


def cell(value):
    if isinstance(value, bytes):
        head = value[:BLOB_PREVIEW].hex()
        return f"x'{head}{'…' if len(value) > BLOB_PREVIEW else ''}' ({len(value)} bytes)"
    if isinstance(value, str) and len(value) > CELL_MAX_CHARS:
        return f"{value[:CELL_MAX_CHARS]}… (+{len(value) - CELL_MAX_CHARS} chars)"
    return value


class SqlBody(BaseModel):
    sql: str = Field(max_length=STATEMENT_MAX_CHARS)
    confirmWrite: bool = False  # noqa: N815 — the JSON API is camelCase
    dryRun: bool = False  # noqa: N815


@router.post("/sql")
def run_sql(body: SqlBody, admin: Annotated[dict, Depends(admin_user)]):
    """
    Execute one statement and return either its rows or its affected-row count.

    A statement is classified as a write by what it *did*, not by how it reads:
    anything that returned no result set or touched a row needs ``confirmWrite``,
    so a ``WITH … DELETE`` cannot slip through as a query. Unconfirmed writes are
    rolled back and reported, which doubles as a dry run — the response says how
    many rows the statement would have hit.

    ``dryRun`` asks for that rehearsal explicitly and for any statement: it runs
    inside the transaction, reports what it saw or would have touched, and rolls
    back unconditionally — a read is answered with its rows, a write with the
    count, and nothing is ever committed.
    """
    sql = body.sql.strip()
    if not sql:
        raise HTTPException(400, "empty statement")

    c = conn()
    # autocommit hands transaction control to us, so DDL rolls back too (under
    # the legacy mode Python only opens a transaction for DML)
    c.isolation_level = None
    try:
        started = time.perf_counter()
        before = c.total_changes
        deadline = time.monotonic() + QUERY_TIMEOUT_S
        try:
            # the deadline guards the admin's statement and nothing else: an
            # expired handler aborts every statement that follows, so leaving it
            # armed would take the rollback and the audit insert down with the
            # query and a timed-out attempt would go unrecorded
            try:
                c.set_progress_handler(
                    lambda: 1 if time.monotonic() > deadline else 0, PROGRESS_INSTRUCTIONS
                )
                c.execute("BEGIN")
                # codeql[py/sql-injection] — executing admin-typed SQL is this
                # console's entire purpose; guarded by admin auth, transactions,
                # write confirmation, timeouts and audit above
                cur = c.execute(sql)
                columns = [d[0] for d in cur.description] if cur.description else []
                rows = (
                    [[cell(v) for v in r] for r in cur.fetchmany(ROW_LIMIT + 1)] if columns else []
                )
            finally:
                c.set_progress_handler(None, 0)
        except sqlite3.Error as e:
            c.rollback()
            _audit(c, admin["id"], "admin_sql_failed", sql)
            raise HTTPException(400, str(e)) from e
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

        changed = c.total_changes - before
        is_write = not columns or changed > 0
        write_rows = max(changed, cur.rowcount, 0)

        if body.dryRun:
            c.rollback()
            _audit(c, admin["id"], "admin_sql_dry_run", sql)
            return {
                "kind": "dry",
                "wouldWrite": is_write,
                "columns": columns,
                "rows": rows[:ROW_LIMIT],
                "rowCount": write_rows if is_write else min(len(rows), ROW_LIMIT),
                "truncated": not is_write and len(rows) > ROW_LIMIT,
                "elapsedMs": elapsed_ms,
            }

        if is_write and not body.confirmWrite:
            c.rollback()
            _audit(c, admin["id"], "admin_sql_rejected", sql)
            raise HTTPException(
                400,
                f"write statement ({leading_keyword(sql) or 'statement'}) needs confirmation;"
                f" it would have affected {write_rows} row{'' if write_rows == 1 else 's'}",
            )

        if is_write:
            c.commit()
            _audit(c, admin["id"], "admin_sql", sql)
            return {
                "kind": "write",
                "columns": [],
                "rows": [],
                "rowCount": write_rows,
                "truncated": False,
                "elapsedMs": elapsed_ms,
            }

        # a read needs nothing committed; rolling back also undoes anything a
        # statement did that neither returned rows nor bumped total_changes
        c.rollback()
        _audit(c, admin["id"], "admin_sql", sql)
        truncated = len(rows) > ROW_LIMIT
        return {
            "kind": "read",
            "columns": columns,
            "rows": rows[:ROW_LIMIT],
            "rowCount": min(len(rows), ROW_LIMIT),
            "truncated": truncated,
            "elapsedMs": elapsed_ms,
        }
    finally:
        c.close()


def _audit(c, uid, kind, sql):
    # a console statement can leave the schema unable to record itself (dropped
    # table, deleted admin row); losing the audit row must not lose the result
    with contextlib.suppress(sqlite3.Error):
        c.execute(
            "INSERT INTO activity_events (user_id, kind, created_at, detail) VALUES (?, ?, ?, ?)",
            (uid, kind, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"), sql[:AUDIT_MAX_CHARS]),
        )
        c.commit()
