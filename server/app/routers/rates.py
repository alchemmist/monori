"""
Exchange rates as an endpoint: read them, pull fresh ones, correct a wrong one.

Every write here changes what stored transactions are worth in the reporting
currency, so each one reprices the user's ledger before answering — the numbers
on screen are never a rate behind the rates.
"""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import current_user
from ..currencies import catalog
from ..currencies import validate as validate_currency
from ..deps import conn
from ..money import base_currency, reprice_user
from ..rates import SOURCE_MANUAL, backfill, rate_table, refresh, store_rates, today_iso

router = APIRouter(prefix="/api/rates", tags=["rates"])

MAX_BACKFILL_DAYS = 90


class RateOverride(BaseModel):
    day: str | None = None
    rubPerUnit: float = Field(gt=0)


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
        on = (day or today_iso())[:10]
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
    user: Annotated[dict, Depends(current_user)],
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
        repriced = reprice_user(c, user["id"])
        c.commit()
        return {"stored": stored, "days": days_fetched, "repriced": repriced}
    finally:
        c.close()


@router.put("/{code}")
def override_rate(code: str, body: RateOverride, user: Annotated[dict, Depends(current_user)]):
    """
    Set a rate by hand — for the day a bank converted at its own rate, or for a
    currency the feed does not carry.
    """
    currency = validate_currency(code)
    c = conn()
    try:
        day = (body.day or today_iso())[:10]
        if not store_rates(c, day, {currency: body.rubPerUnit}, source=SOURCE_MANUAL):
            raise HTTPException(400, f"{currency} is quoted against itself and cannot be set")
        repriced = reprice_user(c, user["id"])
        c.commit()
        return {"code": currency, "day": day, "repriced": repriced}
    finally:
        c.close()
