import sqlite3

from monori.server.app.db import begin_write


def _in_transaction(connection: sqlite3.Connection) -> bool:
    return connection.in_transaction


def test_begin_write_starts_once_and_is_idempotent() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        assert not _in_transaction(connection)
        begin_write(connection)
        assert _in_transaction(connection)
        begin_write(connection)
        assert _in_transaction(connection)
    finally:
        connection.close()
