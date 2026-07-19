"""Standalone bank-sync service.

Runs connectors (Playwright, Chromium) in their own container so the API stays
slim and a browser crash cannot take the API down. Exposed only on the private
compose network — credentials and sessions arrive decrypted from the API, are
held in memory for the duration of a run, and are never written to disk here.

A login that parks on an OTP stays live in ``PENDING`` until the code arrives
on ``/runs/{cid}/sms``, the run is cancelled, or it is replaced by a new run.
"""

import contextlib

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .connectors import base as connectors
from .connectors.base import ConnectorError, SmsRequired

app = FastAPI(title="monori-sync")

PENDING: dict[int, connectors.Connector] = {}


class RunBody(BaseModel):
    bank: str
    kind: str
    credentials: dict
    session: dict | None = None
    since: str | None = None


class SmsBody(BaseModel):
    code: str


def _close_pending(cid):
    old = PENDING.pop(cid, None)
    if old is not None:
        with contextlib.suppress(Exception):
            old.close()


def _done(result):
    return {"status": "done", "rows": result.rows, "session": result.session}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/runs/{cid}")
def start_run(cid: int, body: RunBody):
    _close_pending(cid)
    try:
        cls = connectors.get_connector_class(body.bank, body.kind)
    except ConnectorError as e:
        return {"status": "error", "message": str(e)}
    connector = cls(body.credentials, body.session)
    try:
        return _done(connector.sync(body.since))
    except SmsRequired:
        PENDING[cid] = connector
        return {"status": "awaiting_sms"}
    except ConnectorError as e:
        return {"status": "error", "message": str(e)}


@app.post("/runs/{cid}/sms")
def submit_sms(cid: int, body: SmsBody):
    connector = PENDING.pop(cid, None)
    if connector is None:
        raise HTTPException(409, "no login awaiting a code")
    try:
        return _done(connector.resume_sync(body.code))
    except ConnectorError as e:
        # the failed login is no longer tracked, so close it here or its live
        # browser leaks
        with contextlib.suppress(Exception):
            connector.close()
        return {"status": "error", "message": str(e)}


@app.post("/runs/{cid}/cancel")
def cancel_run(cid: int):
    _close_pending(cid)
    return {"cancelled": cid}
