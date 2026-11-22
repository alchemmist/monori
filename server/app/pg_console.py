# Copyright (c) 2026
"""A scoped financial-data SQL console, not a PostgreSQL cluster administrator."""

from __future__ import annotations

import os
import time
from contextlib import closing
from typing import TYPE_CHECKING

import psycopg
from fastapi import HTTPException
from pglast import parse_sql
from pglast.parser import ParseError
from pglast.stream import RawStream

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import Protocol

    from monori.server.app.db import DatabaseConnection
    from monori.server.app.routers.admin_sql import (
        SqlCell,
        SqlDryResponse,
        SqliteValue,
        SqlResponse,
    )

    class _Body(Protocol):
        sql: str
        dry_run: bool
        confirm_write: bool


TABLES = {
    "accounts",
    "activity_events",
    "alembic_version",
    "bank_connections",
    "budgets",
    "categories",
    "category_group_types",
    "category_groups",
    "feature_usage",
    "import_batches",
    "oidc_identities",
    "splits",
    "transactions",
    "transfer_rejections",
    "transfers",
    "users",
}
NODES = {
    "SelectStmt",
    "UpdateStmt",
    "DeleteStmt",
    "InsertStmt",
    "CreateStmt",
    "ColumnDef",
    "TypeName",
    "TypeCast",
    "ResTarget",
    "A_Const",
    "Integer",
    "Float",
    "String",
    "Boolean",
    "BitString",
    "ColumnRef",
    "RangeVar",
    "Alias",
    "A_Star",
    "A_Expr",
    "FuncCall",
    "BoolExpr",
    "NullTest",
    "BooleanTest",
    "SortBy",
    "JoinExpr",
    "RangeSubselect",
    "SubLink",
    "CommonTableExpr",
    "WithClause",
    "CaseExpr",
    "CaseWhen",
    "CoalesceExpr",
    "MinMaxExpr",
}
FUNCTIONS = {
    "count",
    "min",
    "max",
    "sum",
    "avg",
    "lower",
    "upper",
    "length",
    "char_length",
    "substr",
    "substring",
    "trim",
    "round",
    "abs",
    "date",
    "to_char",
    "date_trunc",
    "nullif",
}
TYPES = {
    "int2",
    "int4",
    "int8",
    "integer",
    "bigint",
    "smallint",
    "numeric",
    "decimal",
    "text",
    "varchar",
    "bool",
    "boolean",
    "date",
    "timestamp",
    "timestamptz",
}


def nodes(x: object) -> Iterator[dict[str, object]]:
    """Yield PostgreSQL AST nodes from the parser's dictionary representation."""
    if isinstance(x, dict):
        if "@" in x:
            yield x
        for value in x.values():
            yield from nodes(value)
    elif isinstance(x, (tuple, list)):
        for value in x:
            yield from nodes(value)


def field_names(node: dict[str, object], field: str) -> list[str]:
    """Extract string names from a parser node field."""
    values = node.get(field)
    if not isinstance(values, (tuple, list)):
        return []
    return [
        value["sval"]
        for value in values
        if isinstance(value, dict) and isinstance(value.get("sval"), str)
    ]


def plan(statement: str, scratch: set[str]) -> tuple[bool, str]:  # noqa: C901, PLR0912
    """Validate a statement and return its write flag and normalized SQL."""
    parsed = parse_sql(statement)
    if len(parsed) != 1:
        raise ValueError("Expected exactly one statement")  # noqa: EM101, TRY003
    root = parsed[0].stmt
    tree_value = root()
    if not isinstance(tree_value, dict) or not isinstance(tree_value.get("@"), str):
        raise TypeError("Invalid PostgreSQL syntax tree")  # noqa: EM101, TRY003
    tree = tree_value
    kind = tree["@"]
    all_nodes = list(nodes(tree))
    ctes = {
        n["ctename"]
        for n in all_nodes
        if n.get("@") == "CommonTableExpr" and isinstance(n.get("ctename"), str)
    }
    if kind not in {"CreateStmt", "SelectStmt", "UpdateStmt", "DeleteStmt", "InsertStmt"}:
        raise ValueError("Unsupported console statement")  # noqa: EM101, TRY003
    for n in all_nodes:
        tag = n.get("@")
        if not isinstance(tag, str):
            raise TypeError("Invalid PostgreSQL syntax tree")  # noqa: EM101, TRY003
        if tag not in NODES or (tag.endswith("Stmt") and n is not tree and tag != "SelectStmt"):
            raise ValueError("Unsupported SQL operation")  # noqa: EM101, TRY003
        if tag == "RangeVar":
            rel = n.get("relname")
            if not isinstance(rel, str):
                raise ValueError("Invalid PostgreSQL syntax tree")  # noqa: EM101, TRY003
            schema = n.get("schemaname")
            creating = kind == "CreateStmt" and n is tree["relation"]
            if (
                n.get("catalogname")
                or rel.startswith(("pg_", "sql_"))
                or rel == "information_schema"
                or n.get("relpersistence") != "p"
            ):
                raise ValueError("Relation outside console scope")  # noqa: EM101, TRY003
            if creating:
                if schema not in (None, "console_scratch") or rel in TABLES:
                    raise ValueError("Create tables only in console_scratch")  # noqa: EM101, TRY003
            elif not (
                (rel in TABLES and schema in (None, "public"))
                or (rel in scratch and schema in (None, "console_scratch"))
                or (rel in ctes and schema is None)
            ):
                raise ValueError("Unknown console table: " + rel)
        elif tag == "FuncCall" and (
            len(field_names(n, "funcname")) != 1 or field_names(n, "funcname")[0] not in FUNCTIONS
        ):
            raise ValueError("Function outside console scope")  # noqa: EM101, TRY003
        elif tag == "TypeName" and (
            field_names(n, "names")[:-1] not in ([], ["pg_catalog"])
            or field_names(n, "names")[-1] not in TYPES
            or n.get("arrayBounds")
        ):
            raise ValueError("Unsupported console type")  # noqa: EM101, TRY003
        elif tag == "A_Expr" and any(
            v
            not in {
                "+",
                "-",
                "*",
                "/",
                "%",
                "=",
                "<>",
                "!=",
                "<",
                ">",
                "<=",
                ">=",
                "~~",
                "!~~",
                "~~*",
                "!~~*",
                "||",
            }
            for v in field_names(n, "name")
        ):
            raise ValueError("Unsupported operator")  # noqa: EM101, TRY003
        elif tag == "CreateStmt" and any(
            n.get(k)
            for k in (
                "tablespacename",
                "accessMethod",
                "inhRelations",
                "ofTypename",
                "partspec",
                "partbound",
                "options",
            )
        ):
            raise ValueError("Only plain scratch tables are supported")  # noqa: EM101, TRY003
        elif tag == "SortBy" and n.get("useOp"):
            raise ValueError("Unsupported ordering operator")  # noqa: EM101, TRY003
    if kind == "CreateStmt":
        root.relation.schemaname = "console_scratch"
    normalized_sql: str = RawStream()(root)  # type: ignore[no-untyped-call]
    return kind != "SelectStmt", normalized_sql


def run(  # noqa: PLR0913, PLR0915
    body: _Body,
    uid: int,
    *,
    statement_max_chars: int,
    query_timeout_s: float,
    row_limit: int,
    cell: Callable[[SqliteValue], SqlCell],
    audit: Callable[[DatabaseConnection, int, str, str], None],
    conn: Callable[[], DatabaseConnection],
    response: Callable[..., SqlResponse],
    dry_response: Callable[..., SqlDryResponse],
) -> SqlResponse | SqlDryResponse:
    """Run a console statement and record its audit outcome."""
    statement = body.sql.strip()
    started = time.monotonic()
    event = "admin_sql_failed"
    if not statement or len(statement) > statement_max_chars:
        raise HTTPException(400, "Invalid SQL length")
    url = os.getenv("MONORI_CONSOLE_DATABASE_URL")
    if not url:
        raise HTTPException(503, "Console credential missing")
    try:
        with psycopg.connect(url, connect_timeout=4) as db:
            db.execute("SET LOCAL search_path = pg_catalog, public, console_scratch")
            db.execute(
                "SELECT set_config('statement_timeout',%s,true)",
                (str(max(1, int(query_timeout_s * 1000))),),
            )
            db.execute("SET LOCAL lock_timeout='2s'")
            scratch = {
                v
                for (v,) in db.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname='console_scratch'"
                )
            }
            write, sql = plan(statement, scratch)
            if not write:
                db.rollback()
                db.execute("SET TRANSACTION READ ONLY")
                db.execute("SET LOCAL search_path = pg_catalog, public, console_scratch")
                db.execute(
                    "SELECT set_config('statement_timeout',%s,true)",
                    (str(max(1, int(query_timeout_s * 1000))),),
                )
            if write:
                db.execute("SELECT pg_advisory_xact_lock(1297043023)")
                if "returning" in sql.lower():
                    raise ValueError(  # noqa: TRY003, TRY301
                        "Use a separate SELECT to view updated rows"  # noqa: EM101
                    )
                cur = db.execute(sql)
                count = max(0, cur.rowcount)
                columns = []
                rows = []
                truncated = False
            else:
                cur = db.cursor(name="monori_result")
                cur.execute(sql)
                description = cur.description
                columns = [d.name for d in description] if description is not None else []
                values = cur.fetchmany(row_limit + 1)
                rows = [[cell(v) for v in row] for row in values[:row_limit]]
                truncated = len(values) > row_limit
                count = len(rows)
                cur.close()
            args = {
                "columns": columns,
                "rows": rows,
                "truncated": truncated,
                "row_count": count,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            }
            if body.dry_run:
                db.rollback()
                event = "admin_sql_dry_run"
                return dry_response(kind="dry", would_write=write, **args)
            if write and not body.confirm_write:
                db.rollback()
                event = "admin_sql_rejected"
                raise HTTPException(
                    400, f"write statement needs confirmation; it would have affected {count} rows"
                )
            db.commit()
            event = "admin_sql"
            return response(kind="write" if write else "read", **args)
    except psycopg.errors.QueryCanceled as exc:
        raise HTTPException(400, "interrupted: statement timeout") from exc
    except (ValueError, ParseError, psycopg.Error) as exc:
        raise HTTPException(400, str(exc).splitlines()[0]) from exc
    finally:
        with closing(conn()) as audit_connection:
            audit(audit_connection, uid, event, statement)
