import sqlite3
from pathlib import Path

import pytest

from monori.server.app import db


@pytest.mark.parametrize("mode", ["DELETE", "WAL"])
def test_bootstrap_configures_journal_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    path = tmp_path / "journal.db"
    monkeypatch.setenv("MONORI_SQLITE_JOURNAL_MODE", mode)
    db.connect(path).close()
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].upper() == mode
    finally:
        connection.close()


def test_bootstrap_rejects_unknown_journal_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "journal.db"
    monkeypatch.setenv("MONORI_SQLITE_JOURNAL_MODE", "memory")
    with pytest.raises(ValueError, match="unsupported SQLite journal mode"):
        db.connect(path)


def test_bootstrap_reports_refused_journal_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "journal.db"
    real_connect = sqlite3.connect

    class Cursor:
        def fetchone(self) -> tuple[str]:
            return ("memory",)

    class Connection:
        def __init__(self, target: Path) -> None:
            self.inner = real_connect(target)

        def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> object:
            if sql.startswith("PRAGMA journal_mode="):
                return Cursor()
            return self.inner.execute(sql, parameters)

        def __getattr__(self, name: str) -> object:
            return getattr(self.inner, name)

    monkeypatch.setattr(db.sqlite3, "connect", Connection)

    with pytest.raises(RuntimeError, match="SQLite refused journal mode DELETE: using MEMORY"):
        vars(db)["_bootstrap"](path)
