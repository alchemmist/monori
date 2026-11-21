# Copyright (c) 2024 Monori
"""Mutation test for monori.server.app.routers.connections._linked_accounts."""

import sqlite3

from monori.server.app.routers.connections import LinkedAccount, _linked_accounts


def test_linked_accounts_filters_by_connection_and_user() -> None:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE accounts (id INTEGER, name TEXT, bank_ref TEXT,"
        " connection_id INTEGER, user_id INTEGER, sort INTEGER)"
    )
    c.execute("INSERT INTO accounts VALUES (7, 'Checking', 'ref-7', 1, 2, 0)")
    c.execute("INSERT INTO accounts VALUES (9, 'Other connection', NULL, 3, 2, 0)")
    c.execute("INSERT INTO accounts VALUES (10, 'Other user', NULL, 1, 4, 0)")
    accounts = _linked_accounts(c, 1, 2)
    c.close()
    assert accounts == [LinkedAccount(7, "Checking", "ref-7")]
