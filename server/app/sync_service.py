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

from fastapi import FastAPI, HTTPException
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from .connectors import base as connectors
from .connectors import tbank_playwright as _tbank_playwright  # noqa: F401
from .connectors.base import ConnectorError, JsonObject, SmsRequiredError, SyncResult

app = FastAPI(title="monori-sync")

log = logging.getLogger(__name__)

SMS_SENT = "A confirmation code was sent to your phone."
CODE_REJECTED = "The bank rejected the code — check it and try again."
SYNC_FAILED = "The bank sync could not be completed."

PENDING: dict[int, connectors.Connector] = {}


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
    return RunStatusResponse(status="error", message=SYNC_FAILED)


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class RunBody:
    """Represent RunBody."""

    bank: str
    kind: str
    credentials: JsonObject
    session: JsonObject | None = None
    since: str | None = None
    accountRef: str | None = None


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class SmsBody:
    """Represent SmsBody."""

    code: str


def _close_pending(cid: int) -> None:
    old = PENDING.pop(cid, None)
    if old is not None:
        with contextlib.suppress(Exception):
            old.close()


def _done(result: SyncResult) -> RunDoneResponse:
    return RunDoneResponse(status="done", rows=result.rows, session=result.session)


@app.get("/health")
def health() -> dict[str, bool]:
    """Handle health."""
    return {"ok": True}


@app.post("/runs/{cid}")
def start_run(cid: int, body: RunBody) -> RunDoneResponse | RunStatusResponse:
    """Handle start run."""
    _close_pending(cid)
    try:
        cls = connectors.get_connector_class(body.bank, body.kind)
    except ConnectorError as e:
        return _error(cid, e)
    connector = cls(body.credentials, body.session, account_ref=body.accountRef)
    try:
        return _done(connector.sync(body.since))
    except SmsRequiredError:
        PENDING[cid] = connector
        return RunStatusResponse(status="awaiting_sms", message=SMS_SENT)
    except ConnectorError as e:
        return _error(cid, e)


@app.post("/runs/{cid}/sms")
def submit_sms(cid: int, body: SmsBody) -> RunDoneResponse | RunStatusResponse:
    """Handle submit sms."""
    connector = PENDING.pop(cid, None)
    if connector is None:
        raise HTTPException(409, "no login awaiting a code")
    try:
        return _done(connector.resume_sync(body.code))
    except SmsRequiredError:
        PENDING[cid] = connector
        return RunStatusResponse(status="awaiting_sms", message=CODE_REJECTED)
    except ConnectorError as e:
        with contextlib.suppress(Exception):
            connector.close()
        return _error(cid, e)


@app.post("/runs/{cid}/cancel")
def cancel_run(cid: int) -> dict[str, int]:
    """Handle cancel run."""
    _close_pending(cid)
    return {"cancelled": cid}
