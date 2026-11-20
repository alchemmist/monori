# Copyright (c) 2024 Monori
"""Tests for the accounts router."""

import sqlite3

from monori.server.app.routers.accounts import _update_icon_image


def test_update_icon_image_skips_write_when_image_is_none() -> None:
    c = sqlite3.connect(":memory:")
    try:
        c.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, icon_image TEXT)")
        c.execute("INSERT INTO accounts (id, icon_image) VALUES (?, ?)", (1, "old.png"))

        _update_icon_image(c, 1, None)

        row = c.execute("SELECT icon_image FROM accounts WHERE id=?", (1,)).fetchone()
        assert row == ("old.png",)
    finally:
        c.close()
