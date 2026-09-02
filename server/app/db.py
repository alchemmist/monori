"""
SQLite access layer. All money amounts are stored as integer kopecks.

The schema has a single canonical definition in ``server/schema.sql``; its history lives as
Alembic revisions in ``server/migrations``. A fresh database
is created straight from ``schema.sql`` and stamped at head; an existing one is
upgraded through the migration chain. Databases from before the alembic switch
carry ``PRAGMA user_version`` — they are adopted by stamping the matching
revision, then upgraded.
"""

import os
import pathlib
import sqlite3
import threading

from alembic import command
from alembic.config import Config

PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1]
DB_PATH = os.environ.get("MONORI_DB", str(pathlib.Path.cwd() / "server" / "data" / "monori.db"))
SCHEMA_PATH = PACKAGE_DIR / "schema.sql"
MIGRATIONS_PATH = PACKAGE_DIR / "migrations"


LEGACY_REVISIONS = ["0001", "0002", "0003", "0004", "0005", "0006"]
JOURNAL_MODES = {"DELETE", "WAL"}
TABLE_INFO_SQL = "SELECT * FROM pragma_table_info(?)"
FOREIGN_KEY_SQL = "SELECT * FROM pragma_foreign_key_list(?)"
SCHEMA_OBJECTS_SQL = (
    "SELECT type, name, tbl_name, sql FROM sqlite_master"
    " WHERE type IN ('table', 'index', 'trigger') AND name NOT LIKE 'sqlite_%'"
)
TABLE_NAMES_SQL = "SELECT name FROM sqlite_master WHERE type='table'"
USER_VERSION_SQL = "PRAGMA user_version"
MEMORY_DATABASE = ":memory:"
SQLITE_SEQUENCE = "sqlite_sequence"
OBJECTS_KEY = "__objects__"
INCOMPATIBLE_SCHEMA_MESSAGE = "database has current table names but incompatible schema metadata"
DEFAULT_JOURNAL_MODE = "DELETE"
type SchemaCell = str | int | None
type SchemaSignature = dict[str, tuple[tuple[SchemaCell, ...], ...]]

_bootstrapped: set[str] = set()
_bootstrap_lock = threading.Lock()


def _alembic_config(path: pathlib.Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_PATH))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def _schema_signature(
    conn: sqlite3.Connection,
    tables: set[str],
) -> SchemaSignature:
    signature = {}
    for table in tables:
        columns = (
            (row[1], row[2], row[3], row[4], row[5])
            for row in conn.execute(TABLE_INFO_SQL, (table,))
        )
        foreign_keys = (tuple(row) for row in conn.execute(FOREIGN_KEY_SQL, (table,)))
        signature[table] = tuple(columns) + tuple(foreign_keys)
    signature[OBJECTS_KEY] = tuple(
        sorted(tuple(row) for row in conn.execute(SCHEMA_OBJECTS_SQL) if str(row[2]) in tables)
    )
    return signature


def _current_schema_signature() -> SchemaSignature:
    memory = sqlite3.connect(MEMORY_DATABASE)
    try:
        memory.executescript(SCHEMA_PATH.read_text())
        tables = {
            str(row[0]) for row in memory.execute(TABLE_NAMES_SQL) if row[0] != SQLITE_SEQUENCE
        }
        return _schema_signature(memory, tables)
    finally:
        memory.close()


def _adopt_unversioned(
    path: pathlib.Path,
    cfg: Config,
    tables: set[str],
    user_version: int,
) -> None:
    current_schema = _current_schema_signature()
    current_tables = set(current_schema) - {OBJECTS_KEY}
    if current_tables <= tables:
        conn = sqlite3.connect(path)
        try:
            actual_schema = _schema_signature(conn, current_tables)
        finally:
            conn.close()
        if actual_schema != current_schema:
            raise RuntimeError(INCOMPATIBLE_SCHEMA_MESSAGE)
        command.stamp(cfg, "head")
        return
    if 0 <= user_version < len(LEGACY_REVISIONS):
        command.stamp(cfg, LEGACY_REVISIONS[user_version])
        command.upgrade(cfg, "head")
        return
    msg = f"unsupported legacy database user_version: {user_version}"
    raise RuntimeError(msg)


def _bootstrap(path: pathlib.Path) -> None:
    conn = sqlite3.connect(path)
    try:
        tables = {r[0] for r in conn.execute(TABLE_NAMES_SQL)}
        user_version = conn.execute(USER_VERSION_SQL).fetchone()[0]
    finally:
        conn.close()

    cfg = _alembic_config(path)
    if "alembic_version" in tables:
        command.upgrade(cfg, "head")
    elif "transactions" in tables:
        _adopt_unversioned(path, cfg, tables, user_version)
    else:
        conn = sqlite3.connect(path)
        try:
            conn.executescript(SCHEMA_PATH.read_text())
            conn.commit()
        finally:
            conn.close()
        command.stamp(cfg, "head")

    journal_mode = os.environ.get("MONORI_SQLITE_JOURNAL_MODE", DEFAULT_JOURNAL_MODE).upper()
    if journal_mode not in JOURNAL_MODES:
        msg = f"unsupported SQLite journal mode: {journal_mode}"
        raise ValueError(msg)
    conn = sqlite3.connect(path)
    try:
        actual_mode = str(conn.execute(f"PRAGMA journal_mode={journal_mode}").fetchone()[0]).upper()
        if actual_mode != journal_mode:
            msg = f"SQLite refused journal mode {journal_mode}: using {actual_mode}"
            raise RuntimeError(msg)
    finally:
        conn.close()


def connect(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Handle connect."""
    path = pathlib.Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = str(path.resolve())
    if key not in _bootstrapped:
        with _bootstrap_lock:
            if key not in _bootstrapped:
                _bootstrap(path)
                _bootstrapped.add(key)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def begin_write(conn: sqlite3.Connection) -> None:
    """Acquire SQLite's write reservation before correlated reads and writes."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
