"""
SQLite access layer. All money amounts are stored as integer kopecks.

The schema has a single canonical definition in ``server/schema.sql``; its
history lives as alembic revisions in ``server/migrations``. A fresh database
is created straight from ``schema.sql`` and stamped at head; an existing one is
upgraded through the migration chain. Databases from before the alembic switch
carry ``PRAGMA user_version`` — they are adopted by stamping the matching
revision, then upgraded.
"""

import os
import pathlib
import sqlite3
import threading

from alembic.config import Config

DB_PATH = os.environ.get(
    "MONORI_DB",
    str(pathlib.Path(__file__).resolve().parent.parent / "data" / "monori.db"),
)

SERVER_DIR = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_PATH = SERVER_DIR / "schema.sql"
MIGRATIONS_PATH = SERVER_DIR / "migrations"


LEGACY_REVISIONS = ["0001", "0002", "0003", "0004", "0005", "0006"]

_bootstrapped: set[str] = set()
_bootstrap_lock = threading.Lock()


def _alembic_config(path: pathlib.Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_PATH))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def _bootstrap(path: pathlib.Path) -> None:
    from alembic import command

    conn = sqlite3.connect(path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    cfg = _alembic_config(path)
    if "alembic_version" in tables:
        command.upgrade(cfg, "head")
    elif "transactions" in tables:
        command.stamp(cfg, LEGACY_REVISIONS[user_version])
        command.upgrade(cfg, "head")
    else:
        conn = sqlite3.connect(path)
        try:
            conn.executescript(SCHEMA_PATH.read_text())
            conn.commit()
        finally:
            conn.close()
        command.stamp(cfg, "head")


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
