# Copyright (c) 2026
"""Transaction serialization preserves database values and split ownership."""

import sqlite3

import pytest
from pydantic import TypeAdapter

from monori.server.app.db_records import SplitRecord, TransactionRecord
from monori.server.app.deps import TransactionResponse, serialize_transactions, serialize_tx
from monori.server.app.domain_types import TransactionSource


@pytest.mark.parametrize("transfer_id", [None, "transfer-7b2c"])
def test_transaction_wire_response_preserves_nullable_ids_and_split_fields(
    transfer_id: str | None,
) -> None:
    transaction = TransactionRecord(
        id=41,
        date="2026-02-03T10:11:12+03:00",
        amount=-12345,
        description="Mixed receipt",
        bank_category="Household",
        mcc="5411",
        category_id=17,
        account_id=23,
        transfer_id=transfer_id,
        comment="Parent note",
        source=TransactionSource.SYNC,
        hidden=True,
    )
    splits = (
        SplitRecord(id=8, transaction_id=41, category_id=19, amount=-2345, comment="Soap"),
        SplitRecord(id=3, transaction_id=41, category_id=17, amount=-10000, comment="Food"),
    )

    response = serialize_tx(transaction, iter(splits))

    assert TypeAdapter(TransactionResponse).dump_python(response, mode="json", by_alias=True) == {
        "id": 41,
        "date": "2026-02-03T10:11:12+03:00",
        "amount": -12345,
        "description": "Mixed receipt",
        "bankCategory": "Household",
        "mcc": "5411",
        "categoryId": 17,
        "accountId": 23,
        "transferId": transfer_id,
        "comment": "Parent note",
        "source": "sync",
        "hidden": True,
        "splits": [
            {"id": 8, "categoryId": 19, "amount": -2345, "comment": "Soap"},
            {"id": 3, "categoryId": 17, "amount": -10000, "comment": "Food"},
        ],
    }


def test_transaction_batch_preserves_row_order_and_groups_ordered_splits() -> None:
    with sqlite3.connect(":memory:") as connection:
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
                amount INTEGER, comment TEXT, sort INTEGER
            );
            """,
        )
        connection.executemany(
            "INSERT INTO transactions VALUES (?, '2026-01-01', -100, 'Receipt', '', '',"
            " NULL, 7, NULL, '', 'manual', 0)",
            ((tx_id,) for tx_id in (11, 22, 33, 44)),
        )
        # Insert out of display order; equal sort values must use the split id.
        connection.executemany(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 11, 7, -30, "Last", 2),
                (9, 11, 8, -50, "Second", 1),
                (5, 11, 9, -20, "First", 1),
                (2, 33, 10, -40, "Other first", 0),
                (3, 33, 11, -60, "Other last", 1),
                (4, 44, 12, -100, "Not requested", 0),
            ],
        )
        cursor = connection.cursor()
        rows = cursor.execute("SELECT * FROM transactions WHERE id != 44 ORDER BY id DESC")

        result = serialize_transactions(cursor, rows)

    assert [transaction.id for transaction in result] == [33, 22, 11]
    assert [
        [(part.id, part.category_id, part.amount, part.comment) for part in transaction.splits]
        for transaction in result
    ] == [
        [(2, 10, -40, "Other first"), (3, 11, -60, "Other last")],
        [],
        [(5, 9, -20, "First"), (9, 8, -50, "Second"), (1, 7, -30, "Last")],
    ]


def test_transaction_batch_accepts_empty_iterator() -> None:
    with sqlite3.connect(":memory:") as connection:
        assert serialize_transactions(connection.cursor(), iter(())) == []
