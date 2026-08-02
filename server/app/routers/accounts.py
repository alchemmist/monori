"""Provide backend functionality."""

import re
import sqlite3
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass as pydantic_dataclass

from app.auth import AuthenticatedUser, current_user
from app.db_records import AccountRecord
from app.deps import AccountResponse, conn, serialize_account
from app.importer import tx_hash

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

TYPES = ("card", "cash", "savings", "other")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

MAX_ICON_IMAGE = 300_000


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class AccountBody:
    """Represent AccountBody."""

    name: str
    type: str | None = None
    icon: str | None = None
    color: str | None = None
    icon_image: str | None = Field(default=None, alias="iconImage")
    currency: str | None = None
    opening_balance: int | None = Field(default=None, alias="openingBalance")
    opening_date: str | None = Field(default=None, alias="openingDate")
    connection_id: int | None = Field(default=None, alias="connectionId")
    bank_ref: str | None = Field(default=None, alias="bankRef")
    card_tails: list[str] | None = Field(default=None, alias="cardTails")


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class AccountPatch:
    """Represent AccountPatch."""

    name: str | None = None
    type: str | None = None
    icon: str | None = None
    color: str | None = None

    icon_image: str | None = Field(default=None, alias="iconImage")
    currency: str | None = None
    opening_balance: int | None = Field(default=None, alias="openingBalance")
    opening_date: str | None = Field(default=None, alias="openingDate")
    archived: bool | None = None

    connection_id: int | None = Field(default=None, alias="connectionId")
    bank_ref: str | None = Field(default=None, alias="bankRef")
    card_tails: list[str] | None = Field(default=None, alias="cardTails")


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class AccountIdResponse:
    """Represent AccountIdResponse."""

    id: int | None


def _owned_connection(c: sqlite3.Connection, connection_id: int, uid: int) -> None:
    if not c.execute(
        "SELECT id FROM bank_connections WHERE id=? AND user_id=?",
        (connection_id, uid),
    ).fetchone():
        raise HTTPException(400, "unknown connection")


def _validate_color(color: str) -> None:
    if not HEX_COLOR.match(color):
        raise HTTPException(400, "color must be a #rrggbb hex string")


def _clean_tails(tails: list[str]) -> str:
    """
    Normalize card tails to the digits of the masked number ('*8181' -> '8181'),.

    deduplicated in order, stored comma-separated.
    """
    cleaned = []
    for raw in tails:
        digits = "".join(ch for ch in str(raw) if ch.isdigit())
        if not digits or len(digits) > 8:  # noqa: PLR2004
            raise HTTPException(400, "card tail must be 1-8 digits")
        if digits not in cleaned:
            cleaned.append(digits)
    return ",".join(cleaned)


def _validate_icon_image(image: str | None) -> None:
    """
    Handle A custom icon is optional; when present it must be an image data URL and.

    stay within the size cap so the snapshot doesn't bloat.
    """
    if not image:
        return
    if len(image) > MAX_ICON_IMAGE or not image.startswith("data:image/"):
        raise HTTPException(400, "icon image must be a data URL image under the size limit")


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class Reorder:
    """Represent Reorder."""

    ids: list[int]


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class ReconcileBody:
    """Represent ReconcileBody."""

    actual_balance: int = Field(alias="actualBalance")


@router.get("")
def list_accounts(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[AccountResponse]:
    """Handle list accounts."""
    uid = user.id
    c = conn()
    try:
        return [
            serialize_account(AccountRecord.from_row(r))
            for r in c.execute(
                "SELECT id, name, type, icon, color, icon_image, currency, sort, archived,"
                " opening_balance, opening_date, connection_id, bank_ref, card_tails"
                " FROM accounts WHERE user_id=? ORDER BY sort, id",
                (uid,),
            )
        ]
    finally:
        c.close()


@router.post("")
def create_account(
    body: AccountBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> AccountIdResponse:
    """Handle create account."""
    uid = user.id
    account_type = body.type or "other"
    icon = body.icon or "wallet"
    color = body.color or "#5b6472"
    currency = body.currency or "RUB"
    opening_balance = body.opening_balance if body.opening_balance is not None else 0
    bank_ref = (body.bank_ref or "").strip()
    if account_type not in TYPES:
        raise HTTPException(400, "type must be one of card, cash, savings, other")
    _validate_color(color)
    _validate_icon_image(body.icon_image)
    c = conn()
    try:
        if c.execute(
            "SELECT id FROM accounts WHERE user_id=? AND name=?",
            (uid, body.name),
        ).fetchone():
            raise HTTPException(409, "account with this name already exists")
        connection_id = body.connection_id
        if connection_id:
            _owned_connection(c, connection_id, uid)
        max_sort = c.execute(
            "SELECT COALESCE(MAX(sort),0) FROM accounts WHERE user_id=?",
            (uid,),
        ).fetchone()[0]
        cur = c.execute(
            """INSERT INTO accounts
               (user_id, name, type, icon, color, icon_image, currency, opening_balance,
                opening_date, sort, connection_id, bank_ref, card_tails)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uid,
                body.name,
                account_type,
                icon,
                color,
                body.icon_image or None,
                currency,
                opening_balance,
                body.opening_date,
                max_sort + 1,
                connection_id or None,
                bank_ref,
                _clean_tails(body.card_tails or []),
            ),
        )
        c.commit()
        return AccountIdResponse(id=cur.lastrowid)
    finally:
        c.close()


@router.patch("/{account_id}")
def patch_account(  # noqa: C901,PLR0912,PLR0915
    account_id: int,
    patch: AccountPatch,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> dict[str, bool]:
    """Handle patch account."""
    uid = user.id
    c = conn()
    try:
        if not c.execute(
            "SELECT id FROM accounts WHERE id=? AND user_id=?",
            (account_id, uid),
        ).fetchone():
            raise HTTPException(404, "account not found")
        name = patch.name
        if name is not None:
            dup = c.execute(
                "SELECT id FROM accounts WHERE user_id=? AND name=? AND id<>?",
                (uid, name, account_id),
            ).fetchone()
            if dup:
                raise HTTPException(409, "account with this name already exists")
            c.execute("UPDATE accounts SET name=? WHERE id=?", (name, account_id))
        account_type = patch.type
        if account_type is not None:
            if account_type not in TYPES:
                raise HTTPException(400, "type must be one of card, cash, savings, other")
            c.execute("UPDATE accounts SET type=? WHERE id=?", (account_type, account_id))
        icon = patch.icon
        if icon is not None:
            c.execute("UPDATE accounts SET icon=? WHERE id=?", (icon, account_id))
        color = patch.color
        if color is not None:
            _validate_color(color)
            c.execute("UPDATE accounts SET color=? WHERE id=?", (color, account_id))
        icon_image = patch.icon_image
        if icon_image is not None:
            _validate_icon_image(icon_image)
            c.execute(
                "UPDATE accounts SET icon_image=? WHERE id=?",
                (icon_image or None, account_id),
            )
        currency = patch.currency
        if currency is not None:
            c.execute("UPDATE accounts SET currency=? WHERE id=?", (currency, account_id))
        opening_balance = patch.opening_balance
        if opening_balance is not None:
            c.execute(
                "UPDATE accounts SET opening_balance=? WHERE id=?",
                (opening_balance, account_id),
            )
        opening_date = patch.opening_date
        if opening_date is not None:
            c.execute("UPDATE accounts SET opening_date=? WHERE id=?", (opening_date, account_id))
        archived = patch.archived
        if archived is not None:
            c.execute(
                "UPDATE accounts SET archived=? WHERE id=?",
                (1 if archived else 0, account_id),
            )
        connection_id = patch.connection_id
        if connection_id is not None:
            if connection_id == 0:
                c.execute("UPDATE accounts SET connection_id=NULL WHERE id=?", (account_id,))
            else:
                _owned_connection(c, connection_id, uid)
                c.execute(
                    "UPDATE accounts SET connection_id=? WHERE id=?",
                    (connection_id, account_id),
                )
        bank_ref = patch.bank_ref
        if bank_ref is not None:
            c.execute(
                "UPDATE accounts SET bank_ref=? WHERE id=?",
                (bank_ref.strip(), account_id),
            )
        card_tails = patch.card_tails
        if card_tails is not None:
            c.execute(
                "UPDATE accounts SET card_tails=? WHERE id=?",
                (_clean_tails(card_tails), account_id),
            )
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.delete("/{account_id}")
def delete_account(
    account_id: int,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    reassign_to: Annotated[int | None, Query(alias="reassignTo")] = None,
) -> dict[str, bool]:
    """
    Handle Deleting an account reassigns its transactions to another account. A.

    transaction must always belong to an account, so a non-empty account cannot.
    be deleted without a reassign target, and the last account cannot be deleted.
    """
    uid = user.id
    c = conn()
    try:
        if not c.execute(
            "SELECT id FROM accounts WHERE id=? AND user_id=?",
            (account_id, uid),
        ).fetchone():
            raise HTTPException(404, "account not found")
        if c.execute("SELECT COUNT(*) FROM accounts WHERE user_id=?", (uid,)).fetchone()[0] == 1:
            raise HTTPException(400, "cannot delete the last account")
        has_tx = c.execute(
            "SELECT 1 FROM transactions WHERE account_id=? LIMIT 1",
            (account_id,),
        ).fetchone()
        if has_tx:
            if reassign_to is None:
                raise HTTPException(400, "account has transactions; a reassign target is required")
            if (
                reassign_to == account_id
                or not c.execute(
                    "SELECT id FROM accounts WHERE id=? AND user_id=?",
                    (reassign_to, uid),
                ).fetchone()
            ):
                raise HTTPException(400, "unknown reassign target")

            moved = c.execute(
                "SELECT id, date, amount, description FROM transactions WHERE account_id=?",
                (account_id,),
            ).fetchall()
            c.executemany(
                "UPDATE transactions SET account_id=?, hash=? WHERE id=?",
                [
                    (
                        reassign_to,
                        tx_hash(reassign_to, r["date"], r["amount"], r["description"]),
                        r["id"],
                    )
                    for r in moved
                ],
            )
        c.execute(
            "UPDATE users SET default_account_id=NULL WHERE default_account_id=?",
            (account_id,),
        )
        c.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.post("/{account_id}/reconcile")
def reconcile_account(
    account_id: int,
    body: ReconcileBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> dict[str, int]:
    """
    Bring an account's computed balance to the real bank balance by posting a.

    single adjustment transaction for the difference. Returns the delta applied.
    """
    uid = user.id
    c = conn()
    try:
        acc = c.execute(
            "SELECT opening_balance FROM accounts WHERE id=? AND user_id=?",
            (account_id, uid),
        ).fetchone()
        if not acc:
            raise HTTPException(404, "account not found")

        total = c.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions"
            " WHERE account_id=? AND hidden = 0"
            " AND (category_id IS NOT NULL OR transfer_id IS NOT NULL"
            "      OR source IN ('transfer', 'adjustment'))",
            (account_id,),
        ).fetchone()[0]
        current = acc["opening_balance"] + total
        delta = body.actual_balance - current
        if delta != 0:
            date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
            desc = "Reconcile adjustment"
            c.execute(
                """INSERT INTO transactions
                   (date, amount, description, account_id, hash, source)
                   VALUES (?, ?, ?, ?, ?, 'adjustment')""",
                (date, delta, desc, account_id, tx_hash(account_id, date, delta, desc)),
            )
            c.commit()
        return {"delta": delta}
    finally:
        c.close()


@router.post("/reorder")
def reorder_accounts(
    body: Reorder,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> dict[str, bool]:
    """Handle reorder accounts."""
    uid = user.id
    c = conn()
    try:
        known = {r["id"] for r in c.execute("SELECT id FROM accounts WHERE user_id=?", (uid,))}
        if set(body.ids) != known:
            raise HTTPException(400, "ids must list every existing account exactly once")
        for sort, aid in enumerate(body.ids, 1):
            c.execute("UPDATE accounts SET sort=? WHERE id=?", (sort, aid))
        c.commit()
        return {"ok": True}
    finally:
        c.close()
