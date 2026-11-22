# Copyright (c) 2026
"""A scoped financial-data SQL console, not a PostgreSQL cluster administrator."""

from __future__ import annotations

import os
import time
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import psycopg
from fastapi import HTTPException
from pglast import parse_sql
from pglast.parser import ParseError
from pglast.stream import RawStream

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from typing import Protocol, TypedDict, Unpack

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

    class _RangeVar(Protocol):
        schemaname: str

    class _RawNode(Protocol):
        relation: _RangeVar

        def __call__(self) -> object: ...

    class _ParsedStatement(Protocol):
        stmt: _RawNode

    class _ParseSql(Protocol):
        def __call__(self, statement: str) -> Sequence[_ParsedStatement]: ...

    class _RawStream(Protocol):
        def __call__(self, node: _RawNode) -> str: ...

    class _ResponseArgs(TypedDict):
        kind: str
        columns: list[str]
        rows: list[list[SqlCell]]
        truncated: bool
        row_count: int
        elapsed_ms: float

    class _DryResponseArgs(_ResponseArgs):
        would_write: bool

    class _ResponseFactory(Protocol):
        def __call__(self, **_kwargs: Unpack[_ResponseArgs]) -> SqlResponse: ...

    class _DryResponseFactory(Protocol):
        def __call__(self, **_kwargs: Unpack[_DryResponseArgs]) -> SqlDryResponse: ...

    class _CellFactory(Protocol):
        def __call__(self, value: SqliteValue) -> SqlCell: ...


@dataclass(frozen=True)
class ConsoleRuntime:
    """Configuration and typed model factories for the PostgreSQL console."""

    statement_max_chars: int
    query_timeout_s: float
    row_limit: int
    cell: _CellFactory
    response: _ResponseFactory
    dry_response: _DryResponseFactory


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
ALLOWED_KINDS = {"CreateStmt", "SelectStmt", "UpdateStmt", "DeleteStmt", "InsertStmt"}
OPERATORS = {
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

EXPECTED_ONE_STATEMENT = "Expected exactly one statement"
INVALID_SYNTAX_TREE = "Invalid PostgreSQL syntax tree"
UNSUPPORTED_STATEMENT = "Unsupported console statement"
UNSUPPORTED_OPERATION = "Unsupported SQL operation"
RELATION_OUT_OF_SCOPE = "Relation outside console scope"
CREATE_ONLY_SCRATCH = "Create tables only in console_scratch"
FUNCTION_OUT_OF_SCOPE = "Function outside console scope"
UNSUPPORTED_TYPE = "Unsupported console type"
UNSUPPORTED_OPERATOR = "Unsupported operator"
PLAIN_SCRATCH_ONLY = "Only plain scratch tables are supported"
UNSUPPORTED_ORDER = "Unsupported ordering operator"


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
    """Extract AST name values, rejecting malformed name-node shapes."""
    values = node.get(field)
    if not isinstance(values, (tuple, list)):
        raise TypeError(INVALID_SYNTAX_TREE)
    result: list[str] = []
    for value in values:
        sval = value.get("sval") if isinstance(value, dict) else None
        if not isinstance(sval, str):
            raise TypeError(INVALID_SYNTAX_TREE)
        result.append(sval)
    return result


def _validate_relation(
    node: dict[str, object], kind: str, root: dict[str, object], scratch: set[str], ctes: set[str]
) -> None:
    rel = node.get("relname")
    if not isinstance(rel, str):
        raise TypeError(INVALID_SYNTAX_TREE)
    schema = node.get("schemaname")
    creating = kind == "CreateStmt" and node is root.get("relation")
    if (
        node.get("catalogname")
        or rel.startswith(("pg_", "sql_"))
        or rel == "information_schema"
        or node.get("relpersistence") != "p"
    ):
        raise ValueError(RELATION_OUT_OF_SCOPE)
    if creating:
        if schema not in (None, "console_scratch") or rel in TABLES:
            raise ValueError(CREATE_ONLY_SCRATCH)
    elif not (
        (rel in TABLES and schema in (None, "public"))
        or (rel in scratch and schema in (None, "console_scratch"))
        or (rel in ctes and schema is None)
    ):
        raise ValueError("Unknown console table: " + rel)


def _validate_function(node: dict[str, object]) -> None:
    names = field_names(node, "funcname")
    if len(names) != 1 or names[0] not in FUNCTIONS:
        raise ValueError(FUNCTION_OUT_OF_SCOPE)


def _validate_type(node: dict[str, object]) -> None:
    names = field_names(node, "names")
    if (
        names[:-1] not in ([], ["pg_catalog"])
        or not names
        or names[-1] not in TYPES
        or node.get("arrayBounds")
    ):
        raise ValueError(UNSUPPORTED_TYPE)


def _validate_operator(node: dict[str, object]) -> None:
    names = field_names(node, "name")
    if not names or any(name not in OPERATORS for name in names):
        raise ValueError(UNSUPPORTED_OPERATOR)


def _validate_create(node: dict[str, object]) -> None:
    restricted = (
        "tablespacename",
        "accessMethod",
        "inhRelations",
        "ofTypename",
        "partspec",
        "partbound",
        "options",
    )
    if any(node.get(field) for field in restricted):
        raise ValueError(PLAIN_SCRATCH_ONLY)


def _validate_node(
    node: dict[str, object], kind: str, root: dict[str, object], scratch: set[str], ctes: set[str]
) -> None:
    tag = node.get("@")
    if not isinstance(tag, str):
        raise TypeError(INVALID_SYNTAX_TREE)
    if tag not in NODES or (tag.endswith("Stmt") and node is not root and tag != "SelectStmt"):
        raise ValueError(UNSUPPORTED_OPERATION)
    if tag == "RangeVar":
        _validate_relation(node, kind, root, scratch, ctes)
    elif tag == "FuncCall":
        _validate_function(node)
    elif tag == "TypeName":
        _validate_type(node)
    elif tag == "A_Expr":
        _validate_operator(node)
    elif tag == "CreateStmt":
        _validate_create(node)
    elif tag == "SortBy" and node.get("useOp"):
        raise ValueError(UNSUPPORTED_ORDER)


def _parse_tree(statement: str) -> tuple[_RawNode, dict[str, object]]:
    """Convert pglast's untyped boundary to the tiny shape this module consumes."""
    parser = cast("_ParseSql", parse_sql)
    parsed = parser(statement)
    if len(parsed) != 1:
        raise ValueError(EXPECTED_ONE_STATEMENT)
    root = parsed[0].stmt
    tree_value = root()
    if not isinstance(tree_value, dict) or not isinstance(tree_value.get("@"), str):
        raise TypeError(INVALID_SYNTAX_TREE)
    return root, tree_value


def plan(statement: str, scratch: set[str]) -> tuple[bool, str]:
    """Validate a statement and return its write flag and normalized SQL."""
    root, tree = _parse_tree(statement)
    kind = tree["@"]
    if not isinstance(kind, str):
        raise TypeError(INVALID_SYNTAX_TREE)
    if kind not in ALLOWED_KINDS:
        raise ValueError(UNSUPPORTED_STATEMENT)
    all_nodes = list(nodes(tree))
    ctes = {
        name
        for node in all_nodes
        if node.get("@") == "CommonTableExpr"
        for name in (node.get("ctename"),)
        if isinstance(name, str)
    }
    for node in all_nodes:
        _validate_node(node, kind, tree, scratch, ctes)
    if kind == "CreateStmt":
        root.relation.schemaname = "console_scratch"
    stream_factory = cast("Callable[[], _RawStream]", RawStream)
    normalized_sql = stream_factory()(root)
    return kind != "SelectStmt", normalized_sql


@dataclass(frozen=True)
class _Execution:
    write: bool
    columns: list[str]
    rows: list[list[SqlCell]]
    truncated: bool
    count: int


def _execute_statement(
    db: psycopg.Connection, statement: str, runtime: ConsoleRuntime
) -> _Execution:
    """Plan and execute one statement within its transaction."""
    db.execute("SET LOCAL search_path = pg_catalog, public, console_scratch")
    timeout = (str(max(1, int(runtime.query_timeout_s * 1000))),)
    db.execute("SELECT set_config('statement_timeout',%s,true)", timeout)
    db.execute("SET LOCAL lock_timeout='2s'")
    scratch = {
        name
        for (name,) in db.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='console_scratch'"
        )
    }
    write, sql = plan(statement, scratch)
    if not write:
        db.rollback()
        db.execute("SET TRANSACTION READ ONLY")
        db.execute("SET LOCAL search_path = pg_catalog, public, console_scratch")
        db.execute("SELECT set_config('statement_timeout',%s,true)", timeout)
    if write:
        db.execute("SELECT pg_advisory_xact_lock(1297043023)")
        if "returning" in sql.lower():
            message = "Use a separate SELECT to view updated rows"
            raise ValueError(message)
        count = max(0, db.execute(sql).rowcount)
        return _Execution(write, [], [], truncated=False, count=count)
    cur = db.cursor(name="monori_result")
    cur.execute(sql)
    columns = [description.name for description in cur.description or ()]
    values = cur.fetchmany(runtime.row_limit + 1)
    rows = [[runtime.cell(value) for value in row] for row in values[: runtime.row_limit]]
    cur.close()
    return _Execution(write, columns, rows, len(values) > runtime.row_limit, len(rows))


def run(
    body: _Body,
    uid: int,
    runtime: ConsoleRuntime,
    audit: Callable[[DatabaseConnection, int, str, str], None],
    conn: Callable[[], DatabaseConnection],
) -> SqlResponse | SqlDryResponse:
    """Run a console statement and record its audit outcome."""
    statement = body.sql.strip()
    started = time.monotonic()
    event = "admin_sql_failed"
    if not statement or len(statement) > runtime.statement_max_chars:
        raise HTTPException(400, "Invalid SQL length")
    url = os.getenv("MONORI_CONSOLE_DATABASE_URL")
    if not url:
        raise HTTPException(503, "Console credential missing")
    try:
        with psycopg.connect(url, connect_timeout=4) as db:
            result = _execute_statement(db, statement, runtime)
            elapsed_ms = round((time.monotonic() - started) * 1000, 1)
            if body.dry_run:
                db.rollback()
                event = "admin_sql_dry_run"
                return runtime.dry_response(
                    kind="dry",
                    would_write=result.write,
                    columns=result.columns,
                    rows=result.rows,
                    truncated=result.truncated,
                    row_count=result.count,
                    elapsed_ms=elapsed_ms,
                )
            if result.write and not body.confirm_write:
                db.rollback()
                event = "admin_sql_rejected"
                raise HTTPException(
                    400,
                    "write statement needs confirmation; "
                    f"it would have affected {result.count} rows",
                )
            db.commit()
            event = "admin_sql"
            return runtime.response(
                kind="write" if result.write else "read",
                columns=result.columns,
                rows=result.rows,
                truncated=result.truncated,
                row_count=result.count,
                elapsed_ms=elapsed_ms,
            )
    except psycopg.errors.QueryCanceled as exc:
        raise HTTPException(400, "interrupted: statement timeout") from exc
    except (ValueError, ParseError, psycopg.Error) as exc:
        raise HTTPException(400, str(exc).splitlines()[0]) from exc
    finally:
        with closing(conn()) as audit_connection:
            audit(audit_connection, uid, event, statement)
