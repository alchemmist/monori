from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, NotRequired, TypedDict, cast

if TYPE_CHECKING:
    import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..deps import conn, serialize_account
from ..importer import tx_hash

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

TYPES = ("card", "cash", "savings", "other")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
# a custom icon is a small downscaled image sent as a data URL; cap the payload
MAX_ICON_IMAGE = 300_000


class AccountBody(TypedDict):
    name: str
    type: NotRequired[str]
    icon: NotRequired[str]
    color: NotRequired[str]
    iconImage: NotRequired[str | None]
    currency: NotRequired[str]
    openingBalance: NotRequired[int]
    openingDate: NotRequired[str | None]
    connectionId: NotRequired[int | None]
    bankRef: NotRequired[str]
    cardTails: NotRequired[list[str]]


class AccountPatch(TypedDict, total=False):
    name: str | None
    type: str | None
    icon: str | None
    color: str | None
    # None = leave as is, "" = clear the custom image, otherwise a new data URL
    iconImage: str | None
    currency: str | None
    openingBalance: int | None
    openingDate: str | None
    archived: bool | None
    # None = leave as is, 0 = unlink from its bank connection
    connectionId: int | None
    bankRef: str | None
    cardTails: list[str] | None


def _owned_connection(c: sqlite3.Connection, connection_id: int, uid: int) -> None:
    if not c.execute(
        "SELECT id FROM bank_connections WHERE id=? AND user_id=?", (connection_id, uid)
    ).fetchone():
        raise HTTPException(400, "unknown connection")


def _validate_color(color: str) -> None:
    if not HEX_COLOR.match(color):
        raise HTTPException(400, "color must be a #rrggbb hex string")


def _clean_tails(tails: list[str]) -> str:
    """
    Normalize card tails to the digits of the masked number ('*8181' -> '8181'),
    deduplicated in order, stored comma-separated.
    """
    cleaned = []
    for raw in tails:
        digits = "".join(ch for ch in str(raw) if ch.isdigit())
        if not digits or len(digits) > 8:
            raise HTTPException(400, "card tail must be 1-8 digits")
        if digits not in cleaned:
            cleaned.append(digits)
    return ",".join(cleaned)


def _validate_icon_image(image: str | None) -> None:
    """
    A custom icon is optional; when present it must be an image data URL and
    stay within the size cap so the snapshot doesn't bloat.
    """
    if not image:
        return
    if len(image) > MAX_ICON_IMAGE or not image.startswith("data:image/"):
        raise HTTPException(400, "icon image must be a data URL image under the size limit")


class Reorder(TypedDict):
    ids: list[int]


class ReconcileBody(TypedDict):
    actualBalance: int


@router.get("")
def list_accounts(
    user: Annotated[dict[str, object], Depends(current_user)],
) -> list[dict[str, object]]:
    uid = cast("int", user["id"])
    c = conn()
    try:
        return [
            serialize_account(r)
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
    body: AccountBody, user: Annotated[dict[str, object], Depends(current_user)]
) -> dict[str, object]:
    uid = cast("int", user["id"])
    account_type = body.get("type")
    if account_type not in TYPES:
        raise HTTPException(400, "type must be one of card, cash, savings, other")
    color = body.get("color")
    if color is None:
        raise HTTPException(400, "color must be a #rrggbb hex string")
    _validate_color(color)
    _validate_icon_image(body.get("iconImage"))
    c = conn()
    try:
        if c.execute(
            "SELECT id FROM accounts WHERE user_id=? AND name=?", (uid, body["name"])
        ).fetchone():
            raise HTTPException(409, "account with this name already exists")
        connection_id = body.get("connectionId")
        if connection_id:
            _owned_connection(c, connection_id, uid)
        max_sort = c.execute(
            "SELECT COALESCE(MAX(sort),0) FROM accounts WHERE user_id=?", (uid,)
        ).fetchone()[0]
        bank_ref = body.get("bankRef")
        if bank_ref is None:
            raise HTTPException(400, "bankRef is required")
        cur = c.execute(
            """INSERT INTO accounts
               (user_id, name, type, icon, color, icon_image, currency, opening_balance,
                opening_date, sort, connection_id, bank_ref, card_tails)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uid,
                body["name"],
                account_type,
                body.get("icon"),
                color,
                body.get("iconImage") or None,
                body.get("currency"),
                body.get("openingBalance"),
                body.get("openingDate"),
                max_sort + 1,
                connection_id or None,
                bank_ref.strip(),
                _clean_tails(body.get("cardTails", [])),
            ),
        )
        c.commit()
        return {"id": cur.lastrowid}
    finally:
        c.close()


@router.patch("/{account_id}")
def patch_account(
    account_id: int,
    patch: AccountPatch,
    user: Annotated[dict[str, object], Depends(current_user)],
) -> dict[str, bool]:
    uid = cast("int", user["id"])
    c = conn()
    try:
        if not c.execute(
            "SELECT id FROM accounts WHERE id=? AND user_id=?", (account_id, uid)
        ).fetchone():
            raise HTTPException(404, "account not found")
        name = patch.get("name")
        if name is not None:
            dup = c.execute(
                "SELECT id FROM accounts WHERE user_id=? AND name=? AND id<>?",
                (uid, name, account_id),
            ).fetchone()
            if dup:
                raise HTTPException(409, "account with this name already exists")
            c.execute("UPDATE accounts SET name=? WHERE id=?", (name, account_id))
        account_type = patch.get("type")
        if account_type is not None:
            if account_type not in TYPES:
                raise HTTPException(400, "type must be one of card, cash, savings, other")
            c.execute("UPDATE accounts SET type=? WHERE id=?", (account_type, account_id))
        icon = patch.get("icon")
        if icon is not None:
            c.execute("UPDATE accounts SET icon=? WHERE id=?", (icon, account_id))
        color = patch.get("color")
        if color is not None:
            _validate_color(color)
            c.execute("UPDATE accounts SET color=? WHERE id=?", (color, account_id))
        icon_image = patch.get("iconImage")
        if icon_image is not None:
            _validate_icon_image(icon_image)
            c.execute(
                "UPDATE accounts SET icon_image=? WHERE id=?",
                (icon_image or None, account_id),
            )
        currency = patch.get("currency")
        if currency is not None:
            c.execute("UPDATE accounts SET currency=? WHERE id=?", (currency, account_id))
        opening_balance = patch.get("openingBalance")
        if opening_balance is not None:
            c.execute(
                "UPDATE accounts SET opening_balance=? WHERE id=?",
                (opening_balance, account_id),
            )
        opening_date = patch.get("openingDate")
        if opening_date is not None:
            c.execute(
                "UPDATE accounts SET opening_date=? WHERE id=?", (opening_date, account_id)
            )
        archived = patch.get("archived")
        if archived is not None:
            c.execute(
                "UPDATE accounts SET archived=? WHERE id=?",
                (1 if archived else 0, account_id),
            )
        connection_id = patch.get("connectionId")
        if connection_id is not None:
            if connection_id == 0:
                c.execute("UPDATE accounts SET connection_id=NULL WHERE id=?", (account_id,))
            else:
                _owned_connection(c, connection_id, uid)
                c.execute(
                    "UPDATE accounts SET connection_id=? WHERE id=?",
                    (connection_id, account_id),
                )
        bank_ref = patch.get("bankRef")
        if bank_ref is not None:
            c.execute(
                "UPDATE accounts SET bank_ref=? WHERE id=?",
                (bank_ref.strip(), account_id),
            )
        card_tails = patch.get("cardTails")
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
    user: Annotated[dict[str, object], Depends(current_user)],
    reassignTo: int | None = None,
) -> dict[str, bool]:
    """
    Deleting an account reassigns its transactions to another account. A
    transaction must always belong to an account, so a non-empty account cannot
    be deleted without a reassign target, and the last account cannot be deleted.
    """
    uid = cast("int", user["id"])
    c = conn()
    try:
        if not c.execute(
            "SELECT id FROM accounts WHERE id=? AND user_id=?", (account_id, uid)
        ).fetchone():
            raise HTTPException(404, "account not found")
        if c.execute("SELECT COUNT(*) FROM accounts WHERE user_id=?", (uid,)).fetchone()[0] == 1:
            raise HTTPException(400, "cannot delete the last account")
        has_tx = c.execute(
            "SELECT 1 FROM transactions WHERE account_id=? LIMIT 1", (account_id,)
        ).fetchone()
        if has_tx:
            if reassignTo is None:
                raise HTTPException(400, "account has transactions; a reassign target is required")
            if (
                reassignTo == account_id
                or not c.execute(
                    "SELECT id FROM accounts WHERE id=? AND user_id=?", (reassignTo, uid)
                ).fetchone()
            ):
                raise HTTPException(400, "unknown reassign target")
            # the dedup hash is account-scoped, so moved rows are re-fingerprinted
            # for their new account or future imports would not dedup against them
            moved = c.execute(
                "SELECT id, date, amount, description FROM transactions WHERE account_id=?",
                (account_id,),
            ).fetchall()
            c.executemany(
                "UPDATE transactions SET account_id=?, hash=? WHERE id=?",
                [
                    (
                        reassignTo,
                        tx_hash(reassignTo, r["date"], r["amount"], r["description"]),
                        r["id"],
                    )
                    for r in moved
                ],
            )
        c.execute(
            "UPDATE users SET default_account_id=NULL WHERE default_account_id=?", (account_id,)
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
    user: Annotated[dict[str, object], Depends(current_user)],
) -> dict[str, int]:
    """
    Bring an account's computed balance to the real bank balance by posting a
    single adjustment transaction for the difference. Returns the delta applied.
    """
    uid = cast("int", user["id"])
    c = conn()
    try:
        acc = c.execute(
            "SELECT opening_balance FROM accounts WHERE id=? AND user_id=?", (account_id, uid)
        ).fetchone()
        if not acc:
            raise HTTPException(404, "account not found")
        # the same rows the account pages count: categorized, transfer legs and
        # earlier adjustments — an unaccepted uncategorized row is outside the
        # balance, so reconciling must not fold it in either
        total = c.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions"
            " WHERE account_id=? AND hidden = 0"
            " AND (category_id IS NOT NULL OR transfer_id IS NOT NULL"
            "      OR source IN ('transfer', 'adjustment'))",
            (account_id,),
        ).fetchone()[0]
        current = acc["opening_balance"] + total
        delta = body["actualBalance"] - current
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
    body: Reorder, user: Annotated[dict[str, object], Depends(current_user)]
) -> dict[str, bool]:
    uid = cast("int", user["id"])
    c = conn()
    try:
        known = {r["id"] for r in c.execute("SELECT id FROM accounts WHERE user_id=?", (uid,))}
        if set(body["ids"]) != known:
            raise HTTPException(400, "ids must list every existing account exactly once")
        for sort, aid in enumerate(body["ids"], 1):
            c.execute("UPDATE accounts SET sort=? WHERE id=?", (sort, aid))
        c.commit()
        return {"ok": True}
    finally:
        c.close()
