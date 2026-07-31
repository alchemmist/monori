import sqlite3
from collections.abc import Iterable
from typing import TypedDict, cast

from app.deps import serialize_transactions


class _Split(TypedDict):
    id: int
    categoryId: int
    amount: int
    comment: str


class _SerializedTx(TypedDict):
    splits: list[_Split]


class SplitCursor:
    def __init__(self) -> None:
        self.chunks: list[list[int]] = []

    def execute(self, _query: str, ids: Iterable[int]) -> list[dict[str, object]]:
        chunk = list(ids)
        self.chunks.append(chunk)
        return [
            {
                "id": tx_id,
                "transaction_id": tx_id,
                "category_id": 7,
                "amount": -1,
                "comment": "part",
            }
            for tx_id in chunk
            if tx_id in {1, 1001}
        ]


def test_serialize_transactions_chunks_split_lookup() -> None:
    rows: list[dict[str, object]] = [
        {
            "id": tx_id,
            "date": "2026-01-01",
            "amount": -1,
            "description": "row",
            "bank_category": "",
            "mcc": "",
            "category_id": None,
            "account_id": 1,
            "transfer_id": None,
            "comment": "",
            "source": "sync",
            "hidden": 0,
        }
        for tx_id in range(1, 1002)
    ]
    cursor = SplitCursor()

    result = cast(
        "list[_SerializedTx]", serialize_transactions(cast("sqlite3.Cursor", cursor), rows)
    )

    assert [len(chunk) for chunk in cursor.chunks] == [500, 500, 1]
    assert result[0]["splits"][0]["categoryId"] == 7
    assert result[-1]["splits"][0]["comment"] == "part"
