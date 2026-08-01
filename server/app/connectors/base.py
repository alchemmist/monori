"""
Connector interface and registry.

A connector is built from a connection's decrypted credentials and cached
session, then asked to :meth:`sync`. Sync returns freshly parsed rows plus an
updated session to cache. If the bank needs an interactive OTP mid-login, sync
raises :class:`SmsRequired`; the caller parks the live connector and later calls
:meth:`resume_sync` with the code the user entered.
"""

from typing import NotRequired, TypedDict

from pydantic import TypeAdapter
from pydantic.dataclasses import dataclass

from ..value_types import JsonObject


class ConnectorParam(TypedDict):
    name: str
    label: str
    secret: bool
    required: bool
    help: NotRequired[str]


class ConnectorInfo(TypedDict):
    bank: str
    kind: str
    label: str
    connectionParams: list[ConnectorParam]
    accountParams: list[ConnectorParam]


@dataclass(slots=True)
class SyncRow:
    date: str
    amount: int
    description: str
    bank_category: str
    mcc: str
    card: str
    account_id: int | None = None
    category_id: int | None = None
    duplicate: bool = False
    hash: str = ""


class ConnectorError(Exception):
    """
    A sync failed for a reason the user should see (auth rejected, bank down).
    """


class SmsRequired(Exception):
    """
    Login reached the OTP step. The caller must collect a code from the user
    and continue the same connector instance via :meth:`Connector.resume_sync`.
    """


@dataclass(slots=True)
class SyncResult:
    """
    Rows pulled in one sync, plus the session to cache for next time.
    """

    rows: list[SyncRow]
    session: JsonObject | None = None


JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
SYNC_RESULT_ADAPTER: TypeAdapter[SyncResult] = TypeAdapter(SyncResult)


class Connector:
    bank = ""
    kind = ""
    label = ""
    #: connectors meant only for tests/demos are hidden from the bank picker
    hidden = False
    #: fields the user fills once per bank login (one form entry each:
    #: name, label, secret, required, help)
    connection_params: list[ConnectorParam] = []
    #: fields locating one bank account within the login, stored per monori
    #: account as its bank_ref
    account_params: list[ConnectorParam] = []

    def __init__(
        self,
        credentials: JsonObject | None,
        session: JsonObject | None = None,
        account_ref: str | None = None,
    ) -> None:
        self.credentials: JsonObject = credentials or {}
        #: opaque per-connector state cached (encrypted) between syncs, e.g. a
        #: browser session; None on the first sync
        self.session: JsonObject | None = session
        #: the bank-side locator of the one account this sync is scoped to
        self.account_ref: str | None = account_ref or None

    def sync(self, since: str | None = None) -> SyncResult:
        """
        Pull transactions changed since ``since`` (ISO date string or None for
        a full pull). Returns a :class:`SyncResult`. Raise :class:`SmsRequired`
        to defer to :meth:`resume_sync`, or :class:`ConnectorError` on failure.
        """
        raise NotImplementedError

    def resume_sync(self, code: str) -> SyncResult:
        """
        Continue a login that raised :class:`SmsRequired`, using the OTP code.
        """
        raise NotImplementedError

    def close(self) -> None:
        """
        Release any live resources (browser, session, worker thread). Called
        when a pending login is replaced, cancelled or deleted. Safe to call more
        than once and on a connector that never started.
        """


REGISTRY: dict[tuple[str, str], type[Connector]] = {}


def register(cls: type[Connector]) -> type[Connector]:
    REGISTRY[(cls.bank, cls.kind)] = cls
    return cls


def get_connector_class(bank: str, kind: str) -> type[Connector]:
    cls = REGISTRY.get((bank, kind))
    if cls is None:
        raise ConnectorError(f"no connector registered for {bank}/{kind}")
    return cls


def available_connectors() -> list[ConnectorInfo]:
    """
    The connectors offered in the UI (registration order, demos excluded).
    """
    return [
        {
            "bank": cls.bank,
            "kind": cls.kind,
            "label": cls.label or cls.bank,
            "connectionParams": cls.connection_params,
            "accountParams": cls.account_params,
        }
        for cls in REGISTRY.values()
        if not cls.hidden
    ]
