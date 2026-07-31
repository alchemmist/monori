#!/usr/bin/env python3
"""
Render the entity-relationship diagram in docs/data-model.md from the canonical
schema.

The schema is not parsed by hand: it is executed into an in-memory SQLite
database and read back through PRAGMA, so the diagram describes what the
database actually becomes, not what a regex thought the DDL said.

    python3 scripts/gen_schema_diagram.py           # rewrite the block
    python3 scripts/gen_schema_diagram.py --check    # fail if it is stale (CI)
"""

import argparse
import sqlite3
import sys
from collections.abc import Mapping
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

ColumnInfo = tuple[int, str, str | None, int, str | None, int]
ForeignKeyInfo = tuple[int, int, str, str, str, str, str, str]
TableInfo = tuple[list[ColumnInfo], list[ForeignKeyInfo]]


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
        columns = list(db.execute(f"PRAGMA table_info({t})"))
        fks = list(db.execute(f"PRAGMA foreign_key_list({t})"))
        out[t] = (columns, fks)
    db.close()
    return out


def diagram(tables: Mapping[str, TableInfo]) -> str:
    lines = ["```mermaid", "erDiagram"]
    for name, (columns, fks) in tables.items():
        # a composite foreign key would repeat the parent per column; mermaid
        # takes one edge per pair, and the schema has none of those anyway
        by_column = {fk[3]: (fk[2], fk[4]) for fk in fks}
        lines.append(f"    {name} {{")
        for _, column, decl_type, notnull, _, pk in columns:
            # mermaid takes several key markers on one attribute comma-separated
            marks = ", ".join(
                filter(None, ["PK" if pk else "", "FK" if column in by_column else ""])
            )
            note = []
            if column in by_column:
                parent, parent_column = by_column[column]
                note.append(f"-> {parent}.{parent_column}")
            if notnull and not pk:
                note.append("required")
            comment = f' "{", ".join(note)}"' if note else ""
            lines.append(
                f"        {decl_type or 'ANY'} {column}{f' {marks}' if marks else ''}{comment}"
            )
        lines.append("    }")
    for name, (columns, fks) in tables.items():
        required = {c[1] for c in columns if c[3]}
        for fk in fks:
            parent, column = fk[2], fk[3]
            # a mandatory child row must have a parent; an optional one may not
            left = "||" if column in required else "|o"
            lines.append(f'    {parent} {left}--o{{ {name} : "{column}"')
    lines.append("```")
    return "\n".join(lines)


def render() -> str:
    return f"{GENERATED_NOTE}\n\n{diagram(introspect(SCHEMA.read_text()))}"


def splice(doc: str, block: str) -> str:
    head, _, rest = doc.partition(START)
    if not rest:
        sys.exit(f"{DOC}: missing the {START} marker")
    _, _, tail = rest.partition(END)
    return f"{head}{START}\n\n{block}\n\n{END}{tail}"


def main() -> None:
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
        print(f"updated {DOC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
