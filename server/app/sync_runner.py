"""
Where bank syncs actually run.

The connections router talks to a :class:`SyncRunner` instead of driving
connectors directly. Two implementations exist: :class:`LocalRunner` executes
the connector in-process (dev, tests, single-container setups) and
:class:`RemoteRunner` forwards the run to the standalone sync service over the
private network (production). ``MONORI_SYNC_URL`` selects the remote one.

Both raise the same exceptions the connectors do — ``SmsRequiredError`` when a login
parks on an OTP, ``ConnectorError`` on failure — plus :class:`NoPendingLoginError`
when an OTP code arrives with no login waiting for it.
"""

import contextlib
import os

import httpx

from .connectors import base as connectors
from .connectors.base import (
    SYNC_RESULT_ADAPTER,
    ConnectorError,
    JsonObject,
    SmsRequiredError,
    SyncResult,
)


class NoPendingLoginError(Exception):
    """An OTP code or cancel arrived but no login is parked for the connection."""


class LocalRunner:
    """Represent LocalRunner."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self._pending: dict[int, connectors.Connector] = {}

    def start(  # noqa: PLR0913
        self,
        cid: int,
        bank: str,
        kind: str,
        credentials: JsonObject,
        session: JsonObject | None,
        since: str | None,
        account_ref: str | None = None,
    ) -> SyncResult:
        """Handle start."""
        self.cancel(cid)
        cls = connectors.get_connector_class(bank, kind)
        connector = cls(credentials, session, account_ref=account_ref)
        try:
            return connector.sync(since)
        except SmsRequiredError:
            self._pending[cid] = connector
            raise

    def resume(self, cid: int, code: str) -> SyncResult:
        """Handle resume."""
        connector = self._pending.pop(cid, None)
        if connector is None:
            raise NoPendingLoginError
        try:
            return connector.resume_sync(code)
        except SmsRequiredError:
            self._pending[cid] = connector
            raise
        except ConnectorError:
            with contextlib.suppress(Exception):
                connector.close()
            raise

    def cancel(self, cid: int) -> None:
        """Handle cancel."""
        old = self._pending.pop(cid, None)
        if old is not None:
            with contextlib.suppress(Exception):
                old.close()


class RemoteRunner:
    """Represent RemoteRunner."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        """Initialize the instance."""
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(600, connect=10),
        )

    @staticmethod
    def _unpack(response: httpx.Response) -> SyncResult:
        try:
            payload = response.json()
        except ValueError as e:
            msg = "sync service returned an invalid response"
            raise ConnectorError(msg) from e
        if not isinstance(payload, dict):
            msg = "sync service returned an invalid response"
            raise ConnectorError(msg)
        status = payload.get("status")
        if status == "done":
            return SYNC_RESULT_ADAPTER.validate_python(
                {"rows": payload.get("rows") or [], "session": payload.get("session")},
            )
        if status == "awaiting_sms":
            raise SmsRequiredError(payload.get("message") or "code sent")
        raise ConnectorError(payload.get("message") or "sync failed")

    def start(  # noqa: PLR0913
        self,
        cid: int,
        bank: str,
        kind: str,
        credentials: JsonObject,
        session: JsonObject | None,
        since: str | None,
        account_ref: str | None = None,
    ) -> SyncResult:
        """Handle start."""
        try:
            r = self._client.post(
                f"/runs/{cid}",
                json={
                    "bank": bank,
                    "kind": kind,
                    "credentials": credentials,
                    "session": session,
                    "since": since,
                    "accountRef": account_ref,
                },
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            msg = f"sync service unavailable: {e}"
            raise ConnectorError(msg) from e
        return self._unpack(r)

    def resume(self, cid: int, code: str) -> SyncResult:
        """Handle resume."""
        try:
            r = self._client.post(f"/runs/{cid}/sms", json={"code": code})
            if r.status_code == 409:  # noqa: PLR2004
                raise NoPendingLoginError
            r.raise_for_status()
        except httpx.HTTPError as e:
            msg = f"sync service unavailable: {e}"
            raise ConnectorError(msg) from e
        return self._unpack(r)

    def cancel(self, cid: int) -> None:
        """Handle cancel."""
        with contextlib.suppress(httpx.HTTPError):
            self._client.post(f"/runs/{cid}/cancel", timeout=httpx.Timeout(5, connect=2))


_runner: LocalRunner | RemoteRunner | None = None


def get_runner() -> LocalRunner | RemoteRunner:
    """Handle get runner."""
    global _runner  # noqa: PLW0603
    if _runner is None:
        url = (os.environ.get("MONORI_SYNC_URL") or "").strip()
        _runner = RemoteRunner(url) if url else LocalRunner()
    return _runner
