# Copyright (c) 2026
"""
Unit tests pinning account patch helpers in routers.accounts.

The mutation gate runs only unit tests (``-m "not integration"``), and the
account update path was previously covered only by integration tests:
mutmut survivors showed that renaming an account, updating its icon image,
card tails, archive flag and duplicate-name protection were all unguarded
at the unit level.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

import monori.server.app.db as dbmod
from monori.server.app.routers.accounts import (
    AccountPatch,
    _clean_tails,
    _ensure_account_name_available,
    _update_account_fields,
    _update_account_tails,
    _validate_account_patch,
)


def _db(tmp_path: Path) -> sqlite3.Connection:
    c = dbmod.connect(str(tmp_path / "t.db"))
    c.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('u@e.co', 'u@e.co', 'h', 't')",
    )
    c.commit()
    return c


def _uid(c: sqlite3.Connection) -> int:
    row = c.execute("SELECT id FROM users").fetchone()
    assert row is not None
    return int(row[0])


def _add_account(c: sqlite3.Connection, name: str = "Card") -> int:
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, ?, 'card', 'RUB', 1)",
        (_uid(c), name),
    )
    return _last_id(c)


def _last_id(c: sqlite3.Connection) -> int:
    row = c.execute("SELECT last_insert_rowid()").fetchone()
    assert row is not None
    return int(row[0])


def test_clean_tails_normalizes_dedupes_and_joins() -> None:
    assert _clean_tails(["*8181", "  8181 ", "1234"]) == "8181,1234"


@pytest.mark.parametrize("bad", ["", "*"])
def test_clean_tails_rejects_digitless_tail(bad: str) -> None:
    with pytest.raises(HTTPException) as e:
        _clean_tails([bad])
    assert e.value.status_code == 400


def test_clean_tails_rejects_long_tail() -> None:
    with pytest.raises(HTTPException) as e:
        _clean_tails(["123456789"])
    assert e.value.status_code == 400


def test_validate_account_patch_rejects_invalid_color_and_image() -> None:
    with pytest.raises(HTTPException) as e:
        _validate_account_patch(AccountPatch(color="red"))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        _validate_account_patch(AccountPatch(icon_image="data:text/plain;base64,AAAA"))
    assert e.value.status_code == 400
    _validate_account_patch(AccountPatch(color="#ff0000", icon_image="data:image/png;base64,AAAA"))


def test_update_account_fields_writes_every_present_field(tmp_path: Path) -> None:
    c = _db(tmp_path)
    account_id = _add_account(c, "Old")
    c.commit()

    _update_account_fields(
        c,
        account_id,
        _uid(c),
        AccountPatch(
            name="New",
            type="cash",
            icon="wallet",
            color="#ff0000",
            currency="USD",
            opening_balance=12345,
            opening_date="2026-01-31",
            archived=True,
            bank_ref="  ref-1  ",
            icon_image="data:image/png;base64,QUJD",
        ),
    )
    c.commit()

    row = c.execute(
        "SELECT name, type, icon, color, currency, opening_balance, opening_date,"
        " archived, bank_ref, icon_image FROM accounts WHERE id=?",
        (account_id,),
    ).fetchone()
    assert row is not None
    assert (
        row["name"],
        row["type"],
        row["icon"],
        row["color"],
        row["currency"],
    ) == ("New", "cash", "wallet", "#ff0000", "USD")
    assert row["opening_balance"] == 12345
    assert row["opening_date"] == "2026-01-31"
    assert row["archived"] == 1
    assert row["bank_ref"] == "ref-1"
    assert row["icon_image"] == "data:image/png;base64,QUJD"


def test_update_icon_image_empty_string_clears_the_image(tmp_path: Path) -> None:
    c = _db(tmp_path)
    account_id = _add_account(c)
    _update_account_fields(
        c, account_id, _uid(c), AccountPatch(icon_image="data:image/png;base64,QUJD")
    )
    _update_account_fields(c, account_id, _uid(c), AccountPatch(icon_image=""))
    row = c.execute("SELECT icon_image FROM accounts WHERE id=?", (account_id,)).fetchone()
    assert row is not None
    assert row["icon_image"] is None


def test_update_account_tails_persists_cleaned_tails(tmp_path: Path) -> None:
    c = _db(tmp_path)
    account_id = _add_account(c)
    _update_account_tails(c, account_id, ["*8181", "8181"])
    row = c.execute("SELECT card_tails FROM accounts WHERE id=?", (account_id,)).fetchone()
    assert row is not None
    assert row["card_tails"] == "8181"
    _update_account_tails(c, account_id, None)
    row = c.execute("SELECT card_tails FROM accounts WHERE id=?", (account_id,)).fetchone()
    assert row is not None
    assert row["card_tails"] == "8181"


def test_ensure_account_name_available_rejects_duplicates_with_409(tmp_path: Path) -> None:
    c = _db(tmp_path)
    first = _add_account(c, "Card")
    second = _add_account(c, "Other")
    c.commit()

    with pytest.raises(HTTPException) as e:
        _ensure_account_name_available(c, second, _uid(c), "Card")
    assert e.value.status_code == 409

    _ensure_account_name_available(c, first, _uid(c), "Card")
    c.execute(
        "INSERT INTO users (email, email_canonical, password_hash, created_at)"
        " VALUES ('u2@e.co', 'u2@e.co', 'h', 't')",
    )
    uid2 = _last_id(c)
    c.execute(
        "INSERT INTO accounts (user_id, name, type, currency, sort)"
        " VALUES (?, 'Salary', 'card', 'RUB', 1)",
        (uid2,),
    )
    c.commit()
    _ensure_account_name_available(c, _last_id(c), uid2, "Card")
    _ensure_account_name_available(c, second, _uid(c), None)


def test_update_account_fields_blocks_renaming_onto_an_existing_name(tmp_path: Path) -> None:
    c = _db(tmp_path)
    _add_account(c, "Card")
    second = _add_account(c, "Other")
    c.commit()

    with pytest.raises(HTTPException) as e:
        _update_account_fields(c, second, _uid(c), AccountPatch(name="Card"))
    assert e.value.status_code == 409
    row = c.execute("SELECT name FROM accounts WHERE id=?", (second,)).fetchone()
    assert row is not None
    assert row["name"] == "Other"

    _update_account_fields(c, second, _uid(c), AccountPatch(name="Salary"))
    row = c.execute("SELECT name FROM accounts WHERE id=?", (second,)).fetchone()
    assert row is not None
    assert row["name"] == "Salary"
