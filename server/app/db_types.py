# Copyright (c) 2026
"""Shared DB-API types for SQLite and PostgreSQL application operations."""

import sqlite3

from monori.server.app.pg_runtime import Connection as PostgresConnection
from monori.server.app.pg_runtime import Cursor as PostgresCursor
from monori.server.app.pg_runtime import Record

type DatabaseRow = sqlite3.Row | Record
type DatabaseCursor = sqlite3.Cursor | PostgresCursor
type DatabaseConnection = sqlite3.Connection | PostgresConnection
