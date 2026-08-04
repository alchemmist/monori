#!/usr/bin/env python3
"""Render the entity-relationship diagram in docs/data-model.md from the canonical schema.

The schema is not parsed by hand: it is executed into an in-memory SQLite
database and read back through PRAGMA, so the diagram describes what the
database actually becomes, not what a regex thought the DDL said.

    python3 scripts/gen_schema_diagram.py           # rewrite the block
    python3 scripts/gen_schema_diagram.py --check    # fail if it is stale (CI)
"""

import argparse
import logging
import sqlite3
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "server" / "schema.sql"
DOC = ROOT / "docs" / "data-model.md"
START = "<!-- schema-diagram:start -->"
END = "<!-- schema-diagram:end -->"
GENERATED_NOTE = (
    "<!-- generated from server/schema.sql by scripts/gen_schema_diagram.py — "
    "run `make schema-diagram` after changing the schema -->"
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    """Introspection entry for a database column."""

    name: str
    declared_type: str | None
    required: bool
    primary_key: bool


@dataclass(frozen=True, slots=True)
class ForeignKeyInfo:
    """Normalized foreign-key relationship extracted from schema."""

    parent_table: str
    child_column: str
    parent_column: str


@dataclass(frozen=True, slots=True)
class TableInfo:
    """Database table definition used to render ER diagram."""

    columns: list[ColumnInfo]
    foreign_keys: list[ForeignKeyInfo]


def introspect(
    schema_sql: str,
) -> dict[str, TableInfo]:
    """Table name → (columns, foreign keys), in declaration order."""
    db = sqlite3.connect(":memory:")
    db.executescript(schema_sql)
    tables = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY rootpage"
        )
    ]
    out: dict[str, TableInfo] = {}
    for t in tables:
        columns = [
            ColumnInfo(str(row[1]), str(row[2]) or None, bool(row[3]), bool(row[5]))
            for row in db.execute(f"PRAGMA table_info({t})")
        ]
        foreign_keys = [
            ForeignKeyInfo(str(row[2]), str(row[3]), str(row[4]))
            for row in db.execute(f"PRAGMA foreign_key_list({t})")
        ]
        out[t] = TableInfo(columns, foreign_keys)
    db.close()
    return out


def diagram(tables: Mapping[str, TableInfo]) -> str:
    """Diagram for this module."""
    lines = ["```mermaid", "erDiagram"]
    for name, table in tables.items():
        # a composite foreign key would repeat the parent per column; mermaid
        # takes one edge per pair, and the schema has none of those anyway
        by_column = {
            foreign_key.child_column: (foreign_key.parent_table, foreign_key.parent_column)
            for foreign_key in table.foreign_keys
        }
        lines.append(f"    {name} {{")
        for column in table.columns:
            # mermaid takes several key markers on one attribute comma-separated
            marks = ", ".join(
                filter(
                    None,
                    [
                        "PK" if column.primary_key else "",
                        "FK" if column.name in by_column else "",
                    ],
                )
            )
            note = []
            if column.name in by_column:
                parent, parent_column = by_column[column.name]
                note.append(f"-> {parent}.{parent_column}")
            if column.required and not column.primary_key:
                note.append("required")
            comment = f' "{", ".join(note)}"' if note else ""
            lines.append(
                f"        {column.declared_type or 'ANY'} {column.name}"
                f"{f' {marks}' if marks else ''}{comment}"
            )
        lines.append("    }")
    for name, table in tables.items():
        required = {column.name for column in table.columns if column.required}
        for foreign_key in table.foreign_keys:
            parent = foreign_key.parent_table
            child_column = foreign_key.child_column
            # a mandatory child row must have a parent; an optional one may not
            left = "||" if child_column in required else "|o"
            lines.append(f'    {parent} {left}--o{{ {name} : "{child_column}"')
    lines.append("```")
    return "\n".join(lines)


def render() -> str:
    """Render for this module."""
    return f"{GENERATED_NOTE}\n\n{diagram(introspect(SCHEMA.read_text()))}"


def splice(doc: str, block: str) -> str:
    """Splice for this module."""
    head, _, rest = doc.partition(START)
    if not rest:
        sys.exit(f"{DOC}: missing the {START} marker")
    _, _, tail = rest.partition(END)
    return f"{head}{START}\n\n{block}\n\n{END}{tail}"


def main() -> None:
    """Run this module as a CLI entrypoint and return its exit code."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify without writing")
    args = ap.parse_args()

    current = DOC.read_text()
    updated = splice(current, render())
    if args.check:
        if current != updated:
            sys.exit(
                f"{DOC.relative_to(ROOT)} is out of date with server/schema.sql"
                " — run `make schema-diagram`"
            )
        return
    if current != updated:
        DOC.write_text(updated)
        logger.info("updated %s", DOC.relative_to(ROOT))


if __name__ == "__main__":
    main()
