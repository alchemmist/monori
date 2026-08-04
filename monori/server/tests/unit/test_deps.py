import sqlite3

from monori.server.app.deps import serialize_transactions


def test_serialize_transactions_chunks_split_lookup() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY, date TEXT, amount INTEGER, description TEXT,
            bank_category TEXT, mcc TEXT, category_id INTEGER, account_id INTEGER,
            transfer_id TEXT, comment TEXT, source TEXT, hidden INTEGER
        );
        CREATE TABLE splits (
            id INTEGER PRIMARY KEY, transaction_id INTEGER, category_id INTEGER,
            amount INTEGER, comment TEXT, sort INTEGER DEFAULT 0
        );
        """,
    )
    connection.executemany(
        "INSERT INTO transactions VALUES (?, '2026-01-01', -1, 'row', '', '',"
        " NULL, 1, NULL, '', 'sync', 0)",
        ((tx_id,) for tx_id in range(1, 1002)),
    )
    connection.executemany(
        "INSERT INTO splits (id, transaction_id, category_id, amount, comment)"
        " VALUES (?, ?, 7, -1, 'part')",
        ((1, 1), (2, 1001)),
    )
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    cursor = connection.cursor()
    rows = cursor.execute("SELECT * FROM transactions ORDER BY id").fetchall()

    result = serialize_transactions(cursor, rows)

    split_queries = [statement for statement in statements if "FROM splits" in statement]
    ids = [statement.partition(" IN (")[2].partition(") ORDER")[0] for statement in split_queries]
    assert [chunk.count(",") + 1 for chunk in ids] == [500, 500, 1]
    assert result[0].splits[0].category_id == 7
    assert result[-1].splits[0].comment == "part"
