# Copyright (c) 2026
"""A scoped financial-data SQL console, not a PostgreSQL cluster administrator."""

import os
import time
from contextlib import closing

import psycopg
from fastapi import HTTPException
from pglast import parse_sql
from pglast.parser import ParseError
from pglast.stream import RawStream

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


def nodes(x):
    if isinstance(x, dict):
        if "@" in x:
            yield x
        for v in x.values():
            yield from nodes(v)
    elif isinstance(x, (tuple, list)):
        for v in x:
            yield from nodes(v)


def plan(statement, scratch):
    parsed = parse_sql(statement)
    if len(parsed) != 1:
        raise ValueError("Expected exactly one statement")
    root = parsed[0].stmt
    tree = root()
    kind = tree["@"]
    all_nodes = list(nodes(tree))
    ctes = {n["ctename"] for n in all_nodes if n["@"] == "CommonTableExpr"}
    if kind not in {"CreateStmt", "SelectStmt", "UpdateStmt", "DeleteStmt", "InsertStmt"}:
        raise ValueError("Unsupported console statement")
    for n in all_nodes:
        tag = n["@"]
        names = lambda field: [x["sval"] for x in n.get(field) or ()]
        if tag not in NODES or (tag.endswith("Stmt") and n is not tree and tag != "SelectStmt"):
            raise ValueError("Unsupported SQL operation")
        if tag == "RangeVar":
            rel = n["relname"]
            schema = n.get("schemaname")
            creating = kind == "CreateStmt" and n is tree["relation"]
            if (
                n.get("catalogname")
                or rel.startswith(("pg_", "sql_"))
                or rel == "information_schema"
                or n.get("relpersistence") != "p"
            ):
                raise ValueError("Relation outside console scope")
            if creating:
                if schema not in (None, "console_scratch") or rel in TABLES:
                    raise ValueError("Create tables only in console_scratch")
            elif not (
                (rel in TABLES and schema in (None, "public"))
                or (rel in scratch and schema in (None, "console_scratch"))
                or (rel in ctes and schema is None)
            ):
                raise ValueError("Unknown console table: " + rel)
        elif tag == "FuncCall" and (
            len(names("funcname")) != 1 or names("funcname")[0] not in FUNCTIONS
        ):
            raise ValueError("Function outside console scope")
        elif tag == "TypeName" and (
            names("names")[:-1] not in ([], ["pg_catalog"])
            or names("names")[-1] not in TYPES
            or n.get("arrayBounds")
        ):
            raise ValueError("Unsupported console type")
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
            for v in names("name")
        ):
            raise ValueError("Unsupported operator")
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
            raise ValueError("Only plain scratch tables are supported")
        elif tag == "SortBy" and n.get("useOp"):
            raise ValueError("Unsupported ordering operator")
    if kind == "CreateStmt":
        root.relation.schemaname = "console_scratch"
    return kind != "SelectStmt", RawStream()(root)


def run(body, uid):
    from monori.server.app.deps import conn
    from monori.server.app.routers import admin_sql as api

    statement = body.sql.strip()
    started = time.monotonic()
    event = "admin_sql_failed"
    if not statement or len(statement) > api.STATEMENT_MAX_CHARS:
        raise HTTPException(400, "Invalid SQL length")
    url = os.getenv("MONORI_CONSOLE_DATABASE_URL")
    if not url:
        raise HTTPException(503, "Console credential missing")
    try:
        with psycopg.connect(url, connect_timeout=4) as db:
            db.execute("SET LOCAL search_path = pg_catalog, public, console_scratch")
            db.execute(
                "SELECT set_config('statement_timeout',%s,true)",
                (str(max(1, int(api.QUERY_TIMEOUT_S * 1000))),),
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
                    (str(max(1, int(api.QUERY_TIMEOUT_S * 1000))),),
                )
            if write:
                db.execute("SELECT pg_advisory_xact_lock(1297043023)")
                if "returning" in sql.lower():
                    raise ValueError("Use a separate SELECT to view updated rows")
                cur = db.execute(sql)
                count = max(0, cur.rowcount)
                columns = []
                rows = []
                truncated = False
            else:
                cur = db.cursor(name="monori_result")
                cur.execute(sql)
                columns = [d.name for d in cur.description]
                values = cur.fetchmany(api.ROW_LIMIT + 1)
                rows = [[api.cell(v) for v in row] for row in values[: api.ROW_LIMIT]]
                truncated = len(values) > api.ROW_LIMIT
                count = len(rows)
                cur.close()
            args = dict(
                columns=columns,
                rows=rows,
                truncated=truncated,
                row_count=count,
                elapsed_ms=round((time.monotonic() - started) * 1000, 1),
            )
            if body.dry_run:
                db.rollback()
                event = "admin_sql_dry_run"
                return api.SqlDryResponse(kind="dry", would_write=write, **args)
            if write and not body.confirm_write:
                db.rollback()
                event = "admin_sql_rejected"
                raise HTTPException(
                    400, f"write statement needs confirmation; it would have affected {count} rows"
                )
            db.commit()
            event = "admin_sql"
            return api.SqlResponse(kind="write" if write else "read", **args)
    except psycopg.errors.QueryCanceled as exc:
        raise HTTPException(400, "interrupted: statement timeout") from exc
    except (ValueError, ParseError, psycopg.Error) as exc:
        raise HTTPException(400, str(exc).splitlines()[0]) from exc
    finally:
        with closing(conn()) as audit:
            api._audit(audit, uid, event, statement)
