"""Where bank syncs actually run.

The connections router talks to a :class:`SyncRunner` instead of driving
connectors directly. Two implementations exist: :class:`LocalRunner` executes
the connector in-process (dev, tests, single-container setups) and
:class:`RemoteRunner` forwards the run to the standalone sync service over the
private network (production). ``MONORI_SYNC_URL`` selects the remote one.

Both raise the same exceptions the connectors do — ``SmsRequired`` when a login
parks on an OTP, ``ConnectorError`` on failure — plus :class:`NoPendingLogin`
when an OTP code arrives with no login waiting for it.
"""

import contextlib
import os

import httpx

from .connectors import base as connectors
from .connectors.base import ConnectorError, SmsRequired, SyncResult


class NoPendingLogin(Exception):
    """An OTP code or cancel arrived but no login is parked for the connection."""


class LocalRunner:
    def __init__(self):
        self._pending: dict[int, connectors.Connector] = {}

    def start(self, cid, bank, kind, credentials, session, since):
        self.cancel(cid)
        cls = connectors.get_connector_class(bank, kind)
        connector = cls(credentials, session)
        try:
            return connector.sync(since)
        except SmsRequired:
            self._pending[cid] = connector
            raise

    def resume(self, cid, code):
        connector = self._pending.pop(cid, None)
        if connector is None:
            raise NoPendingLogin
        try:
            return connector.resume_sync(code)
        except ConnectorError:
            # the failed login is no longer tracked, so close it here or its
            # live browser leaks
            with contextlib.suppress(Exception):
                connector.close()
            raise

    def cancel(self, cid):
        old = self._pending.pop(cid, None)
        if old is not None:
            with contextlib.suppress(Exception):
                old.close()


class RemoteRunner:
    def __init__(self, base_url, client=None):
        # browser logins are slow; the read timeout must outlive a full one
        self._client = client or httpx.Client(
            base_url=base_url, timeout=httpx.Timeout(600, connect=10)
        )

    @staticmethod
    def _unpack(response):
        try:
            payload = response.json()
        except ValueError as e:
            raise ConnectorError("sync service returned an invalid response") from e
        if not isinstance(payload, dict):
            raise ConnectorError("sync service returned an invalid response")
        status = payload.get("status")
        if status == "done":
            return SyncResult(payload.get("rows") or [], payload.get("session"))
        if status == "awaiting_sms":
            raise SmsRequired("code sent")
        raise ConnectorError(payload.get("message") or "sync failed")

    def start(self, cid, bank, kind, credentials, session, since):
        try:
            r = self._client.post(
                f"/runs/{cid}",
                json={
                    "bank": bank,
                    "kind": kind,
                    "credentials": credentials,
                    "session": session,
                    "since": since,
                },
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ConnectorError(f"sync service unavailable: {e}") from e
        return self._unpack(r)

    def resume(self, cid, code):
        try:
            r = self._client.post(f"/runs/{cid}/sms", json={"code": code})
            if r.status_code == 409:
                raise NoPendingLogin
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ConnectorError(f"sync service unavailable: {e}") from e
        return self._unpack(r)

    def cancel(self, cid):
        # best-effort cleanup on user-facing endpoints: must fail fast (not
        # the 600 s sync timeout) and must not block deleting a connection
        # when the sync service is down
        with contextlib.suppress(httpx.HTTPError):
            self._client.post(f"/runs/{cid}/cancel", timeout=httpx.Timeout(5, connect=2))


_runner = None


def get_runner():
    global _runner
    if _runner is None:
        url = os.environ.get("MONORI_SYNC_URL")
        _runner = RemoteRunner(url) if url else LocalRunner()
    return _runner
