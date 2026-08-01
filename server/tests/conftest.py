import os
import pathlib
import sys
import tempfile
from typing import TypedDict

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.deps import IdResponse
from app.routers.auth_router import TokenResponse
from app.routers.transfers import TransferIdResponse

STATEMENT = (
    "05.01.2026 10:00:00\t05.01.2026\t*1\tOK\t-100,00\tRUB\t-100,00\tRUB\t\tSuper\t5411\tLenta\t0\t0\t-100,00\n"  # noqa: E501
    "06.01.2026 11:00:00\t06.01.2026\t*1\tOK\t-200,00\tRUB\t-200,00\tRUB\t\tSuper\t5411\tOkey\t0\t0\t-200,00\n"  # noqa: E501
)


class _PreviewRow(TypedDict, total=False):
    accountId: int | None
    amount: int
    bank_category: str
    card: str
    categoryId: int | None
    date: str
    description: str
    duplicate: bool
    hash: str
    mcc: str


class _PreviewResponse(TypedDict):
    rows: list[_PreviewRow]
    errors: list[str]


class _SnapshotAccount(TypedDict):
    id: int
    name: str
    type: str
    icon: str
    color: str
    iconImage: str | None
    currency: str
    sort: int
    archived: bool
    openingBalance: int
    openingDate: str | None
    connectionId: int | None
    bankRef: str
    cardTails: list[str]


class _SnapshotGroup(TypedDict):
    id: int
    name: str
    sort: int
    kind: str


class _SnapshotCategory(TypedDict):
    id: int
    groupId: int
    name: str
    keywords: str
    sort: int
    archived: bool
    goalTarget: int | None
    goalStatus: str | None
    goalTargetDate: str | None


class _SnapshotSplit(TypedDict):
    id: int
    categoryId: int
    amount: int
    comment: str


class _SnapshotTransaction(TypedDict):
    id: int
    date: str
    amount: int
    description: str
    bankCategory: str
    mcc: str
    categoryId: int | None
    accountId: int
    transferId: int | None
    comment: str
    source: str
    hidden: bool
    splits: list[_SnapshotSplit]


class _SnapshotBudget(TypedDict):
    categoryId: int
    year: int
    month: int
    amount: int


class _SnapshotConnection(TypedDict):
    id: int
    bank: str
    kind: str
    status: str
    lastSync: str | None
    lastError: str | None
    hasCredentials: bool
    createdAt: str
    updatedAt: str


class _SnapshotTransfer(TypedDict):
    id: int
    outTxId: int
    inTxId: int
    origin: str
    note: str
    createdAt: str


class _Snapshot(TypedDict):
    accounts: list[_SnapshotAccount]
    groups: list[_SnapshotGroup]
    categories: list[_SnapshotCategory]
    transactions: list[_SnapshotTransaction]
    transactionsTotal: int
    transfers: list[_SnapshotTransfer]
    budgets: list[_SnapshotBudget]
    connections: list[_SnapshotConnection]


def _fresh_app_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    monkeypatch.setenv("MONORI_DB", db_path)
    import app.db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
    dbmod.connect(db_path).close()

    from app.main import app as fastapi_app

    return TestClient(fastapi_app)


def login_as(client: TestClient, email: str, password: str = "hunter2pw") -> dict[str, str]:
    """
    Register (if needed) and sign in; returns a bearer-token header dict.
    """
    client.post("/api/auth/register", json={"email": email, "password": password})
    r = client.post("/api/auth/token", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    token = TypeAdapter(TokenResponse).validate_python(r.json())
    return {"Authorization": f"Bearer {token.access_token}"}


def _response_id(response: IdResponse) -> int:
    assert response.id is not None
    return response.id


@pytest.fixture()
def anon(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    A client with no credentials attached (the DB is fresh and empty).
    """
    return _fresh_app_client(monkeypatch)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    A client signed in as the default test user; every request carries the
    bearer token via default headers.
    """
    c = _fresh_app_client(monkeypatch)
    c.headers.update(login_as(c, "tester@example.com"))
    return c


class Api:
    """
    Thin helper over the HTTP client for arranging test state. Bodies that
    should always succeed assert 200; error paths are exercised with the raw
    `client` in the tests themselves.
    """

    statement = STATEMENT

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def group(self, name: str, kind: str = "expense") -> int:
        r = self.client.post("/api/groups", json={"name": name, "kind": kind})
        assert r.status_code == 200, r.text
        return _response_id(TypeAdapter(IdResponse).validate_python(r.json()))

    def category(self, name: str, group_id: int, keywords: str = "") -> int:
        r = self.client.post(
            "/api/categories", json={"name": name, "groupId": group_id, "keywords": keywords}
        )
        assert r.status_code == 200, r.text
        return _response_id(TypeAdapter(IdResponse).validate_python(r.json()))

    def account(
        self,
        name: str,
        *,
        type: str = "cash",
        icon: str = "wallet",
        color: str = "#5b6472",
        currency: str = "RUB",
        openingBalance: int = 0,
        bankRef: str = "",
        cardTails: list[str] | None = None,
    ) -> int:
        body = {
            "name": name,
            "type": type,
            "icon": icon,
            "color": color,
            "currency": currency,
            "openingBalance": openingBalance,
            "bankRef": bankRef,
            "cardTails": cardTails or [],
        }
        r = self.client.post("/api/accounts", json=body)
        assert r.status_code == 200, r.text
        return _response_id(TypeAdapter(IdResponse).validate_python(r.json()))

    def default_account(self) -> int:
        return self.snapshot()["accounts"][0]["id"]

    def tx(
        self,
        date: str,
        amount: int,
        *,
        accountId: int | None = None,
        categoryId: int | None = None,
        description: str = "",
        comment: str = "",
    ) -> int:
        r = self.client.post(
            "/api/transactions",
            json={
                "date": date,
                "amount": amount,
                "accountId": accountId or self.default_account(),
                "categoryId": categoryId,
                "description": description,
                "comment": comment,
            },
        )
        assert r.status_code == 200, r.text
        return _response_id(TypeAdapter(IdResponse).validate_python(r.json()))

    def transfer(
        self,
        from_account: int,
        to_account: int,
        amount: int,
        date: str = "2026-01-10T12:00:00",
        comment: str = "",
    ) -> str:
        r = self.client.post(
            "/api/transfers",
            json={
                "fromAccountId": from_account,
                "toAccountId": to_account,
                "amount": amount,
                "date": date,
                "comment": comment,
            },
        )
        assert r.status_code == 200, r.text
        return TypeAdapter(TransferIdResponse).validate_python(r.json()).transferId

    def snapshot(self) -> _Snapshot:
        return TypeAdapter(_Snapshot).validate_python(self.client.get("/api/snapshot").json())

    def cat(self, cat_id: int) -> _SnapshotCategory:
        return next(c for c in self.snapshot()["categories"] if c["id"] == cat_id)

    def acct(self, account_id: int) -> _SnapshotAccount:
        return next(a for a in self.snapshot()["accounts"] if a["id"] == account_id)

    def tx_by(self, tx_id: int) -> _SnapshotTransaction:
        return next(t for t in self.snapshot()["transactions"] if t["id"] == tx_id)

    def preview(self, text: str, account_id: int | None = None) -> list[_PreviewRow]:
        body = {"text": text, "accountId": account_id or self.default_account()}
        response = self.client.post("/api/import/preview", json=body)
        return TypeAdapter(_PreviewResponse).validate_python(response.json())["rows"]


@pytest.fixture()
def api(client: TestClient) -> Api:
    return Api(client)
