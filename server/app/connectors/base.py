"""Connector interface and registry.

A connector is built from a connection's decrypted credentials and cached
session, then asked to :meth:`sync`. Sync returns freshly parsed rows plus an
updated session to cache. If the bank needs an interactive OTP mid-login, sync
raises :class:`SmsRequired`; the caller parks the live connector and later calls
:meth:`resume_sync` with the code the user entered.
"""


class ConnectorError(Exception):
    """A sync failed for a reason the user should see (auth rejected, bank down)."""


class SmsRequired(Exception):
    """Login reached the OTP step. The caller must collect a code from the user
    and continue the same connector instance via :meth:`Connector.resume_sync`."""


class SyncResult:
    """Rows pulled in one sync, plus the session to cache for next time."""

    def __init__(self, rows, session=None):
        self.rows = rows
        self.session = session


class Connector:
    bank = ""
    kind = ""
    #: connectors meant only for tests/demos are hidden from the bank picker
    hidden = False

    def __init__(self, credentials, session=None, profile_dir=None):
        self.credentials = credentials or {}
        self.session = session
        #: a stable on-disk directory a connector may use to persist a browser
        #: profile (cookies, device identity) across syncs, so it stays logged in
        self.profile_dir = profile_dir

    def sync(self, since=None):
        """Pull transactions changed since ``since`` (ISO date string or None for
        a full pull). Returns a :class:`SyncResult`. Raise :class:`SmsRequired`
        to defer to :meth:`resume_sync`, or :class:`ConnectorError` on failure."""
        raise NotImplementedError

    def resume_sync(self, code):
        """Continue a login that raised :class:`SmsRequired`, using the OTP code."""
        raise NotImplementedError


REGISTRY: dict[tuple[str, str], type[Connector]] = {}


def register(cls):
    REGISTRY[(cls.bank, cls.kind)] = cls
    return cls


def get_connector_class(bank, kind):
    cls = REGISTRY.get((bank, kind))
    if cls is None:
        raise ConnectorError(f"no connector registered for {bank}/{kind}")
    return cls


def available_connectors():
    """The connectors offered in the UI (registration order, demos excluded)."""
    return [{"bank": cls.bank, "kind": cls.kind} for cls in REGISTRY.values() if not cls.hidden]
