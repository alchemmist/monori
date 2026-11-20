# Copyright (c) 2024 Monori
"""Tests for the accounts router."""

import sqlite3

from monori.server.app.routers.accounts import _update_icon_image


def test_update_icon_image_writes_when_image_is_not_none() -> None:
    c = sqlite3.connect(":memory:")
    try:
        c.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, icon_image TEXT)")
        c.execute("INSERT INTO accounts (id, icon_image) VALUES (?, ?)", (1, "old.png"))

        _update_icon_image(c, 1, "new.png")

        row = c.execute("SELECT icon_image FROM accounts WHERE id=?", (1,)).fetchone()
        assert row == ("new.png",)
    finally:
        c.close()
