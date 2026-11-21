"""Isolate integration tests in the disposable Unix-socket cluster created by run.sh."""

import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from import_postgres_0021 import transfer


@pytest.fixture(autouse=True)
def pg_target(monkeypatch, tmp_path):
    from monori.server.app import db as dbmod

    root = Path(os.environ["MONORI_TEST_CLUSTER"])
    if not root.is_absolute() or not root.name.startswith("monori-pgtests."):
        raise ValueError("Expected a private test cluster")
    url = f"postgresql:///monori_test?host={root}&port=55442"
    with psycopg.connect(url) as db:
        actual = db.execute("SELECT current_setting('data_directory')").fetchone()[0]
        if Path(actual).resolve() != (root / "db").resolve():
            raise ValueError("Wrong test server")
        db.execute("DROP SCHEMA public CASCADE")
        db.execute("CREATE SCHEMA public")
        path = tmp_path / "src.sqlite"
        dbmod.connect(path).close()
        with closing(sqlite3.connect(path)) as src:
            transfer(src, db)
    monkeypatch.setenv("MONORI_DATABASE_URL", url)
