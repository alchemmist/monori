from app.deps import serialize_transactions


class SplitCursor:
    def __init__(self):
        self.chunks = []

    def execute(self, query, ids):
        if "refund_links" in query:
            return []
        self.chunks.append(list(ids))
        return [
            {
                "id": tx_id,
                "transaction_id": tx_id,
                "category_id": 7,
                "amount": -1,
                "comment": "part",
            }
            for tx_id in ids
            if tx_id in {1, 1001}
        ]


def test_serialize_transactions_chunks_split_lookup():
    rows = [
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

    result = serialize_transactions(cursor, rows)

    assert [len(chunk) for chunk in cursor.chunks] == [500, 500, 1]
    assert result[0]["splits"][0]["categoryId"] == 7
    assert result[-1]["splits"][0]["comment"] == "part"
