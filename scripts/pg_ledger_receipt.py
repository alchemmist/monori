"""Compare source and destination using the same private HMAC key (stdin).

Outputs aggregate counts and keyed digests only. No names, amounts, descriptions,
account identifiers or credentials are emitted. Capture on a consistent snapshot.
"""
import hashlib
import hmac
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

QUERIES = {
    'account_totals': '''SELECT a.id, a.user_id, a.currency, a.opening_balance,
        COUNT(t.id), COALESCE(SUM(t.amount),0) FROM accounts a
        LEFT JOIN transactions t ON t.account_id=a.id
        GROUP BY a.id,a.user_id,a.currency,a.opening_balance ORDER BY a.id''',
    'transaction_amounts': '''SELECT id, account_id, amount, transfer_id
        FROM transactions ORDER BY id''',
    'transfer_legs': '''SELECT x.id,x.user_id,x.out_tx_id,o.account_id,o.amount,
        x.in_tx_id,i.account_id,i.amount FROM transfers x
        LEFT JOIN transactions o ON o.id=x.out_tx_id
        LEFT JOIN transactions i ON i.id=x.in_tx_id ORDER BY x.id''',
}


def receipt(db, key):
    result = {}
    for name, query in QUERIES.items():
        mac = hmac.new(key, name.encode(), hashlib.sha256)
        count = 0
        for row in db.execute(query):
            mac.update(json.dumps(tuple(row), separators=(',', ':'), default=str).encode() + b'\n')
            count += 1
        result[name] = {'rows': count, 'hmac_sha256': mac.hexdigest()}
    return result


if __name__ == '__main__':
    key = sys.stdin.buffer.read()
    if len(key) < 32:
        sys.exit('Require a private comparison key of at least 32 bytes on stdin')
    if len(sys.argv) == 2:
        db = sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + '?mode=ro', uri=True)
        db.execute('BEGIN')
    else:
        import psycopg
        db = psycopg.connect(os.environ['DATABASE_URL'])
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    with closing(db):
        print(json.dumps(receipt(db, key), sort_keys=True))
