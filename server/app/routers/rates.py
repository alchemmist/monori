"""
Exchange rates as an endpoint: read them, pull fresh ones, correct a wrong one.

Every write here changes what stored transactions are worth in the reporting
currency, so each one reprices every ledger before answering — the numbers on
screen are never a rate behind the rates.

Reading is everyone's; writing is the admin's. What a currency was worth on a
day is one shared fact, not a per-user preference, and the table has no owner
column — so a hand-set rate would move every user's totals at once. The
per-user case (my bank converted at its own rate) is already served where it
belongs: a transfer records the amount that actually arrived.
"""

from datetime import date as date_cls
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..admin import admin_user
from ..auth import current_user
from ..currencies import catalog
from ..currencies import validate as validate_currency
from ..deps import conn
from ..money import base_currency, reprice_all
from ..rates import SOURCE_MANUAL, backfill, rate_table, refresh, store_rates, today_iso

router = APIRouter(prefix="/api/rates", tags=["rates"])

MAX_BACKFILL_DAYS = 90


class RateOverride(BaseModel):
    day: str | None = None
    rubPerUnit: float = Field(gt=0)


def _iso_day(day):
    """
    An ISO date, or a 400.

    Rates are looked up by comparing ``day`` as text, which only orders
    correctly for ``YYYY-MM-DD`` — a malformed one would sort into the wrong
    place and quietly return the wrong rate.
    """
    day = (day or today_iso())[:10]
    try:
        return date_cls.fromisoformat(day).isoformat()
    except ValueError as e:
        raise HTTPException(400, f"day must be an ISO date (YYYY-MM-DD), got {day!r}") from e


@router.get("")
def get_rates(
    user: Annotated[dict, Depends(current_user)],
    day: str | None = Query(default=None),
):
    """
    What each currency is worth on ``day``, alongside the registry itself so a
    settings screen needs one request rather than two.
    """
    c = conn()
    try:
        on = _iso_day(day)
        return {
            "day": on,
            "baseCurrency": base_currency(c, user["id"]),
            "currencies": catalog(),
            "rates": rate_table(c, on),
        }
    finally:
        c.close()


@router.post("/refresh")
def refresh_rates(
    admin: Annotated[dict, Depends(admin_user)],
    days: int = Query(default=0, ge=0, le=MAX_BACKFILL_DAYS),
):
    """
    Pull today's rates from the CBR, and optionally the last ``days`` of them
    for a ledger that has been running without any.
    """
    c = conn()
    try:
        try:
            stored = refresh(c)
            days_fetched = 1 + (backfill(c, days) if days else 0)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"could not reach the rate feed: {e}") from e
        repriced = reprice_all(c)
        c.commit()
        return {"stored": stored, "days": days_fetched, "repriced": repriced}
    finally:
        c.close()


@router.put("/{code}")
def override_rate(code: str, body: RateOverride, admin: Annotated[dict, Depends(admin_user)]):
    """
    Set a rate by hand — for a day the feed never published, or a currency it
    does not carry.
    """
    currency = validate_currency(code)
    day = _iso_day(body.day)
    c = conn()
    try:
        if not store_rates(c, day, {currency: body.rubPerUnit}, source=SOURCE_MANUAL):
            raise HTTPException(400, f"{currency} is quoted against itself and cannot be set")
        repriced = reprice_all(c)
        c.commit()
        return {"code": currency, "day": day, "repriced": repriced}
    finally:
        c.close()
