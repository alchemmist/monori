import sqlite3

from app.db import begin_write


def test_begin_write_starts_once_and_is_idempotent():
    connection = sqlite3.connect(":memory:")
    try:
        assert not connection.in_transaction
        begin_write(connection)
        assert connection.in_transaction
        begin_write(connection)
        assert connection.in_transaction
    finally:
        connection.close()
