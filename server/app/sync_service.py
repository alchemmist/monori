"""
Standalone bank-sync service.

Runs connectors (Playwright, Chromium) in their own container so the API stays
slim and a browser crash cannot take the API down. Exposed only on the private
compose network — credentials and sessions arrive decrypted from the API, are
held in memory for the duration of a run, and are never written to disk here.

A login that parks on an OTP stays live in ``PENDING`` until the code arrives
on ``/runs/{cid}/sms``, the run is cancelled, or it is replaced by a new run.
"""

import contextlib
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import monotonic

from fastapi import FastAPI, HTTPException
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass as pydantic_dataclass

from monori.common import JsonObject
from monori.server.app.connectors import base as connectors
from monori.server.app.connectors.base import (
    ConnectorError,
    PublicConnectorError,
    SmsRequiredError,
    SyncResult,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Release every pending connector when FastAPI stops."""
    yield
    shutdown()


app = FastAPI(title="monori-sync", lifespan=lifespan)

log = logging.getLogger(__name__)

SMS_SENT = "A confirmation code was sent to your phone."
CODE_REJECTED = "The bank rejected the code — check it and try again."
SYNC_FAILED = "The bank sync could not be completed."

PENDING_TTL_SECONDS = 600
PENDING_CAPACITY = 8


@dataclass(frozen=True)
class PendingSession:
    """Own a connector until its SMS deadline."""

    connector: connectors.Connector
    expires_at: float


PENDING: dict[int, PendingSession] = {}
PENDING_LOCK = threading.RLock()


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class RunStatusResponse:
    """Represent RunStatusResponse."""

    status: str
    message: str | None = None


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class RunDoneResponse:
    """Represent RunDoneResponse."""

    status: str
    rows: list[connectors.SyncRow]
    session: JsonObject | None


def _error(cid: int, error: Exception) -> RunStatusResponse:
    log.warning("sync run %s failed: %s", cid, error)
    if isinstance(error, PublicConnectorError):
        return RunStatusResponse(status=connectors.PUBLIC_ERROR_STATUS, message=str(error))
    return RunStatusResponse(status="error", message=SYNC_FAILED)


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class RunBody:
    """Represent RunBody."""

    bank: str
    kind: str
    credentials: JsonObject
    session: JsonObject | None = None
    since: str | None = None
    account_ref: str | None = Field(default=None, alias="accountRef")


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class SmsBody:
    """Represent SmsBody."""

    code: str


def _close_connector(connector: connectors.Connector) -> None:
    with contextlib.suppress(Exception):
        connector.close()


def _close_pending(cid: int) -> None:
    old = PENDING.pop(cid, None)
    if old is not None:
        _close_connector(old.connector)


def _expire_pending() -> None:
    now = monotonic()
    for cid, pending in list(PENDING.items()):
        if pending.expires_at <= now:
            _close_pending(cid)


def _park(cid: int, connector: connectors.Connector) -> None:
    PENDING[cid] = PendingSession(connector, monotonic() + PENDING_TTL_SECONDS)


def close_all_pending() -> None:
    """Close and forget every connector waiting for SMS."""
    with PENDING_LOCK:
        for cid in list(PENDING):
            _close_pending(cid)


def shutdown() -> None:
    """Release pending browser sessions during application shutdown."""
    close_all_pending()


def _done(result: SyncResult) -> RunDoneResponse:
    return RunDoneResponse(status="done", rows=result.rows, session=result.session)


@app.get("/health")
def health() -> dict[str, bool]:
    """Handle health."""
    return {"ok": True}


@app.post("/runs/{cid}")
def start_run(cid: int, body: RunBody) -> RunDoneResponse | RunStatusResponse:
    """Handle start run."""
    with PENDING_LOCK:
        _expire_pending()
        _close_pending(cid)
        if len(PENDING) >= PENDING_CAPACITY:
            raise HTTPException(429, "too many logins awaiting a code")
        try:
            cls = connectors.get_connector_class(body.bank, body.kind)
        except ConnectorError as e:
            return _error(cid, e)
        connector = cls(body.credentials, body.session, account_ref=body.account_ref)
        try:
            result = _done(connector.sync(body.since))
            _close_connector(connector)
        except SmsRequiredError:
            _park(cid, connector)
            return RunStatusResponse(status="awaiting_sms", message=SMS_SENT)
        except ConnectorError as e:
            _close_connector(connector)
            return _error(cid, e)
        else:
            return result


@app.post("/runs/{cid}/sms")
def submit_sms(cid: int, body: SmsBody) -> RunDoneResponse | RunStatusResponse:
    """Handle submit sms."""
    with PENDING_LOCK:
        _expire_pending()
        pending = PENDING.pop(cid, None)
        if pending is None:
            raise HTTPException(409, "no login awaiting a code")
        connector = pending.connector
        try:
            result = _done(connector.resume_sync(body.code))
            _close_connector(connector)
        except SmsRequiredError:
            _park(cid, connector)
            return RunStatusResponse(status="awaiting_sms", message=CODE_REJECTED)
        except ConnectorError as e:
            _close_connector(connector)
            return _error(cid, e)
        else:
            return result


@app.post("/runs/{cid}/cancel")
def cancel_run(cid: int) -> dict[str, int]:
    """Handle cancel run."""
    with PENDING_LOCK:
        _expire_pending()
        _close_pending(cid)
    return {"cancelled": cid}
