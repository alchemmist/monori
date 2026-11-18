# Copyright (c) 2026
import sqlite3

import pytest

from monori.server.app.db_records import AccountRecord
from monori.server.app.deps import serialize_accounts, serialize_transactions
from monori.server.app.domain_types import AccountType


def test_serialize_transactions_chunks_split_lookup() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY, date TEXT, amount INTEGER, description TEXT,
            bank_category TEXT, mcc TEXT, category_id INTEGER, account_id INTEGER,
            transfer_id TEXT, comment TEXT, source TEXT, hidden INTEGER,
            currency TEXT, base_amount INTEGER
        );
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, currency TEXT);
        INSERT INTO accounts VALUES (1, 'RUB');
        CREATE TABLE splits (
            id INTEGER PRIMARY KEY, transaction_id INTEGER, category_id INTEGER,
            amount INTEGER, comment TEXT, sort INTEGER DEFAULT 0
        );
        """,
    )
    connection.executemany(
        "INSERT INTO transactions VALUES (?, '2026-01-01', -1, 'row', '', '',"
        " NULL, 1, NULL, '', 'sync', 0, 'RUB', -1)",
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
    account_queries = [statement for statement in statements if "FROM accounts" in statement]
    ids = [statement.partition(" IN (")[2].partition(") ORDER")[0] for statement in split_queries]
    assert [chunk.count(",") + 1 for chunk in ids] == [500, 500, 1]
    assert len(account_queries) == 1
    assert result[0].splits[0].category_id == 7
    assert result[-1].splits[0].comment == "part"


def test_serialize_transactions_converts_to_the_account_currency() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, currency TEXT);
        INSERT INTO accounts VALUES (1, 'GEL');
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY, date TEXT, amount INTEGER, description TEXT,
            bank_category TEXT, mcc TEXT, category_id INTEGER, account_id INTEGER,
            transfer_id TEXT, comment TEXT, source TEXT, hidden INTEGER,
            currency TEXT, base_amount INTEGER
        );
        INSERT INTO transactions VALUES (
            1, '2026-07-01', 100, '', '', '', NULL, 1, NULL, '', 'manual', 0, 'USD', 100
        );
        CREATE TABLE splits (
            id INTEGER PRIMARY KEY, transaction_id INTEGER, category_id INTEGER,
            amount INTEGER, comment TEXT, sort INTEGER DEFAULT 0
        );
        CREATE TABLE exchange_rates (
            day TEXT, code TEXT, rub_per_unit REAL, source TEXT,
            PRIMARY KEY (day, code)
        );
        INSERT INTO exchange_rates VALUES ('2026-07-01', 'USD', 90, 'manual');
        INSERT INTO exchange_rates VALUES ('2026-07-01', 'GEL', 30, 'manual');
        """,
    )
    cursor = connection.cursor()

    result = serialize_transactions(cursor, cursor.execute("SELECT * FROM transactions"))

    assert result[0].amount == 100
    assert result[0].currency == "USD"
    assert result[0].account_amount == 300


def test_serialize_transactions_rejects_a_missing_account() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, currency TEXT);
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY, date TEXT, amount INTEGER, description TEXT,
            bank_category TEXT, mcc TEXT, category_id INTEGER, account_id INTEGER,
            transfer_id TEXT, comment TEXT, source TEXT, hidden INTEGER,
            currency TEXT, base_amount INTEGER
        );
        INSERT INTO transactions VALUES (
            1, '2026-07-01', 100, '', '', '', NULL, 99, NULL, '', 'manual', 0, 'USD', 100
        );
        CREATE TABLE splits (
            id INTEGER PRIMARY KEY, transaction_id INTEGER, category_id INTEGER,
            amount INTEGER, comment TEXT, sort INTEGER DEFAULT 0
        );
        """,
    )
    cursor = connection.cursor()

    with pytest.raises(RuntimeError, match="account currency is unavailable"):
        serialize_transactions(cursor, cursor.execute("SELECT * FROM transactions"))


def test_serialize_accounts_batches_earliest_transaction_dates() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, base_currency TEXT);
        INSERT INTO users VALUES (1, 'RUB');
        CREATE TABLE transactions (account_id INTEGER, date TEXT);
        INSERT INTO transactions VALUES (1, '2026-01-01'), (1, '2026-07-01');
        INSERT INTO transactions VALUES (2, '2026-03-01');
        """,
    )
    accounts = [
        AccountRecord(
            id=account_id,
            name=f"Account {account_id}",
            type=AccountType.CASH,
            icon="wallet",
            color="#000000",
            icon_image=None,
            currency="RUB",
            sort=account_id,
            archived=False,
            opening_balance=0,
            opening_date=None,
            connection_id=None,
            bank_ref="",
            card_tails="",
        )
        for account_id in (1, 2)
    ]
    statements: list[str] = []
    connection.set_trace_callback(statements.append)

    result = serialize_accounts(connection, 1, accounts)

    assert [account.opening_base_amount for account in result] == [0, 0]
    assert sum("MIN(date)" in statement for statement in statements) == 1
    assert sum("FROM users" in statement for statement in statements) == 1


def test_empty_account_serialization_needs_no_database_queries() -> None:
    connection = sqlite3.connect(":memory:")
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    try:
        assert serialize_accounts(connection, 999, []) == []
        assert statements == []
    finally:
        connection.close()
