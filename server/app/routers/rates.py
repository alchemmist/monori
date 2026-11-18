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
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass as pydantic_dataclass

from monori.server.app.admin import admin_user
from monori.server.app.auth import AuthenticatedUser, current_user
from monori.server.app.currencies import catalog
from monori.server.app.currencies import validate as validate_currency
from monori.server.app.deps import conn
from monori.server.app.money import base_currency, reprice_all
from monori.server.app.rates import (
    SOURCE_MANUAL,
    backfill,
    rate_table,
    refresh,
    store_rates,
    today_iso,
)

router = APIRouter(prefix="/api/rates", tags=["rates"])

MAX_BACKFILL_DAYS = 90


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class RateOverride:
    "Represent a manually supplied exchange rate."

    rub_per_unit: float = Field(gt=0, alias="rubPerUnit")
    day: str | None = None


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class CurrencyResponse:
    "Represent one supported currency."

    code: str
    name: str
    symbol: str
    minor_units: int = Field(alias="minorUnits")


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class RateResponse:
    "Represent one dated exchange rate."

    code: str
    rate: float
    day: str
    source: str
    stale: bool


@pydantic_dataclass(config=ConfigDict(extra="forbid", populate_by_name=True))
class RatesResponse:
    "Represent the currency catalog and rates for a requested day."

    day: str
    currencies: list[CurrencyResponse]
    rates: list[RateResponse]
    base_currency: str = Field(alias="baseCurrency")


def _iso_day(day: str | None) -> str:
    """
    Return an ISO date, or raise a 400 response.

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
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    day: Annotated[str | None, Query()] = None,
) -> RatesResponse:
    """
    Return what each currency is worth on ``day``.

    Include the registry so a
    settings screen needs one request rather than two.
    """
    c = conn()
    try:
        on = _iso_day(day)
        return RatesResponse(
            day=on,
            baseCurrency=base_currency(c, user.id),
            currencies=[
                CurrencyResponse(
                    code=str(row["code"]),
                    name=str(row["name"]),
                    symbol=str(row["symbol"]),
                    minorUnits=int(row["minorUnits"]),
                )
                for row in catalog()
            ],
            rates=[
                RateResponse(
                    code=str(row["code"]),
                    rate=float(row["rate"]),
                    day=str(row["day"]),
                    source=str(row["source"]),
                    stale=bool(row["stale"]),
                )
                for row in rate_table(c, on)
            ],
        )
    finally:
        c.close()


@router.post("/refresh")
def refresh_rates(
    _admin: Annotated[AuthenticatedUser, Depends(admin_user)],
    days: Annotated[int, Query(ge=0, le=MAX_BACKFILL_DAYS)] = 0,
) -> dict[str, int]:
    """
    Pull today's rates from the CBR, and optionally the last ``days`` of them.

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
def override_rate(
    code: str,
    body: RateOverride,
    _admin: Annotated[AuthenticatedUser, Depends(admin_user)],
) -> dict[str, str | int]:
    """
    Set a rate by hand — for a day the feed never published, or a currency it.

    does not carry.
    """
    currency = validate_currency(code)
    day = _iso_day(body.day)
    c = conn()
    try:
        if not store_rates(c, day, {currency: body.rub_per_unit}, source=SOURCE_MANUAL):
            raise HTTPException(400, f"{currency} is quoted against itself and cannot be set")
        repriced = reprice_all(c)
        c.commit()
        return {"code": currency, "day": day, "repriced": repriced}
    finally:
        c.close()
