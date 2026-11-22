# Copyright (c) 2026
"""PostgreSQL-backed implementation of the application's small DB-API subset."""

import re
import sqlite3
from decimal import Decimal

import psycopg
from psycopg import ClientCursor

IDENTITIES = {
    "accounts",
    "activity_events",
    "bank_connections",
    "categories",
    "category_groups",
    "category_group_types",
    "import_batches",
    "splits",
    "transactions",
    "users",
}


class Record(tuple):
    def keys(self):
        return self._fields

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                key = self._fields.index(key)
            except ValueError as exc:
                raise IndexError(key) from exc
        return super().__getitem__(key)


def record_factory(cur):
    names = tuple(d.name for d in cur.description or ())

    def build(values):
        r = Record(
            int(v) if isinstance(v, Decimal) and v == v.to_integral_value() else v for v in values
        )
        r._fields = names
        return r

    return build


class Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.inner = conn.raw.cursor()
        self.lastrowid = None

    def __iter__(self):
        return iter(self.inner)

    def __getattr__(self, key):
        return getattr(self.inner, key)

    def execute(self, sql, params=()):
        statement = sql.strip()
        lowered = statement.lower()
        if lowered == "pragma foreign_keys=on":
            statement = "SELECT 1"
        elif lowered == "pragma page_count":
            statement = "SELECT pg_database_size(current_database())"
        elif lowered == "pragma page_size":
            statement = "SELECT 1"
        if lowered.startswith(("insert ", "update ", "delete ")) or lowered == "begin immediate":
            self.conn.lock()
        if lowered == "begin immediate":
            return self
        if "SELECT value FROM json_each(?)" in statement:
            typ = "text" if "t.source IN" in statement else "bigint"
            statement = statement.replace(
                "SELECT value FROM json_each(?)",
                f"SELECT value::{typ} FROM json_array_elements_text(?::json) AS elem(value)",
            )
        if lowered.startswith("insert or ignore into "):
            statement = (
                re.sub("^insert or ignore into ", "INSERT INTO ", statement, flags=re.IGNORECASE)
                + " ON CONFLICT DO NOTHING"
            )
        match = re.match(r"INSERT\s+INTO\s+(\w+)", statement, re.IGNORECASE)
        identity = bool(
            match and match[1].lower() in IDENTITIES and "RETURNING" not in statement.upper()
        )
        if identity:
            statement += " RETURNING id"
        if params:
            statement = statement.replace("%", "%%")
            statement = (
                re.sub(r"(?<!:):(\w+)", r"%(\1)s", statement)
                if isinstance(params, dict)
                else statement.replace("?", "%s")
            )
        try:
            self.inner.execute(statement, params or None)
        except psycopg.IntegrityError as exc:
            raise sqlite3.IntegrityError("database integrity constraint") from exc
        self.lastrowid = self.inner.fetchone()[0] if identity and self.inner.rowcount else None
        return self


class Connection:
    def __init__(self, url):
        self.raw = psycopg.connect(
            url, cursor_factory=ClientCursor, row_factory=record_factory, connect_timeout=5
        )
        self.locked = False

    def lock(self):
        if not self.locked:
            self.raw.execute("SELECT pg_advisory_xact_lock(1297043023)").close()
            self.locked = True

    def cursor(self):
        return Cursor(self)

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def executemany(self, sql, rows):
        cur = self.cursor()
        for params in rows:
            cur.execute(sql, params)
        return cur

    def commit(self):
        self.raw.commit()
        self.locked = False

    def rollback(self):
        self.raw.rollback()
        self.locked = False

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, typ, _value, _traceback):
        if typ is None:
            self.commit()
        else:
            self.rollback()
