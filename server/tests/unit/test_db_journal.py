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
