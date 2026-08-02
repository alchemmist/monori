"""
Connector interface and registry.

A connector is built from a connection's decrypted credentials and cached
session, then asked to :meth:`sync`. Sync returns freshly parsed rows plus an
updated session to cache. If the bank needs an interactive OTP mid-login, sync
raises :class:`SmsRequiredError`; the caller parks the live connector and later calls
:meth:`resume_sync` with the code the user entered.
"""

from typing import ClassVar

from pydantic import ConfigDict, Field, JsonValue, TypeAdapter
from pydantic.dataclasses import dataclass as pydantic_dataclass

type JsonObject = dict[str, JsonValue]


@pydantic_dataclass
class ConnectorParam:
    """Represent ConnectorParam."""

    name: str
    label: str = ""
    secret: bool = False
    required: bool = False
    help: str | None = None


@pydantic_dataclass(config=ConfigDict(populate_by_name=True, serialize_by_alias=True))
class ConnectorInfo:
    """Represent ConnectorInfo."""

    bank: str
    kind: str
    label: str
    connection_params: list[ConnectorParam] = Field(serialization_alias="connectionParams")
    account_params: list[ConnectorParam] = Field(serialization_alias="accountParams")

    def __getattr__(self, name: str) -> list[ConnectorParam]:
        """Provide camelCase compatibility aliases for serialized connector params."""
        if name == "connectionParams":
            return self.connection_params
        if name == "accountParams":
            return self.account_params
        raise AttributeError(name)


@pydantic_dataclass
class SyncRow:
    """Represent SyncRow."""

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
    """A sync failed for a reason the user should see (auth rejected, bank down)."""


class SmsRequiredError(Exception):
    """
    Login reached the OTP step. The caller must collect a code from the user.

    and continue the same connector instance via :meth:`Connector.resume_sync`.
    """


@pydantic_dataclass
class SyncResult:
    """Rows pulled in one sync, plus the session to cache for next time."""

    rows: list[SyncRow]
    session: JsonObject | None = None


JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
SYNC_RESULT_ADAPTER: TypeAdapter[SyncResult] = TypeAdapter(SyncResult)


class Connector:
    """Represent Connector."""

    bank = ""
    kind = ""
    label = ""

    hidden = False

    connection_params: ClassVar[list[ConnectorParam]] = []

    account_params: ClassVar[list[ConnectorParam]] = []

    def __init__(
        self,
        credentials: JsonObject | None,
        session: JsonObject | None = None,
        account_ref: str | None = None,
    ) -> None:
        """Initialize the instance."""
        self.credentials: JsonObject = credentials or {}

        self.session: JsonObject | None = session

        self.account_ref: str | None = account_ref or None

    def sync(self, since: str | None = None) -> SyncResult:
        """
        Pull transactions changed since ``since`` (ISO date string or None for.

        a full pull). Returns a :class:`SyncResult`. Raise :class:`SmsRequiredError`
        to defer to :meth:`resume_sync`, or :class:`ConnectorError` on failure.
        """
        raise NotImplementedError

    def resume_sync(self, code: str) -> SyncResult:
        """Continue a login that raised :class:`SmsRequiredError`, using the OTP code."""
        raise NotImplementedError

    def close(self) -> None:
        """
        Release any live resources (browser, session, worker thread). Called.

        when a pending login is replaced, cancelled or deleted. Safe to call more.
        than once and on a connector that never started.
        """


REGISTRY: dict[tuple[str, str], type[Connector]] = {}


def register(cls: type[Connector]) -> type[Connector]:
    """Handle register."""
    REGISTRY[(cls.bank, cls.kind)] = cls
    return cls


def get_connector_class(bank: str, kind: str) -> type[Connector]:
    """Handle get connector class."""
    cls = REGISTRY.get((bank, kind))
    if cls is None:
        msg = f"no connector registered for {bank}/{kind}"
        raise ConnectorError(msg)
    return cls


def available_connectors() -> list[ConnectorInfo]:
    """Handle The connectors offered in the UI (registration order, demos excluded)."""
    return [
        ConnectorInfo(
            bank=cls.bank,
            kind=cls.kind,
            label=cls.label or cls.bank,
            connection_params=cls.connection_params,
            account_params=cls.account_params,
        )
        for cls in REGISTRY.values()
        if not cls.hidden
    ]
