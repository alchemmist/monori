# Copyright (c) 2024 Monori
"""Mutation test for monori.server.app.routers.connections._linked_accounts."""

import sqlite3

from monori.server.app.routers.connections import _linked_accounts


def test_linked_accounts_returns_id() -> None:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE accounts (id INTEGER, name TEXT, bank_ref TEXT,"
        " connection_id INTEGER, user_id INTEGER, sort INTEGER)"
    )
    c.execute("INSERT INTO accounts VALUES (7, 'Checking', NULL, 1, 2, 0)")
    accounts = _linked_accounts(c, 1, 2)
    assert len(accounts) == 1
    assert accounts[0].id == 7
