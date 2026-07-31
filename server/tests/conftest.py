import os
import pathlib
import sys
import tempfile
from typing import TypedDict, cast

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

STATEMENT = (
    "05.01.2026 10:00:00\t05.01.2026\t*1\tOK\t-100,00\tRUB\t-100,00\tRUB\t\tSuper\t5411\tLenta\t0\t0\t-100,00\n"  # noqa: E501
    "06.01.2026 11:00:00\t06.01.2026\t*1\tOK\t-200,00\tRUB\t-200,00\tRUB\t\tSuper\t5411\tOkey\t0\t0\t-200,00\n"  # noqa: E501
)


class _IdResponse(TypedDict):
    id: int


class _TransferIdResponse(TypedDict):
    transferId: int


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
    return {"Authorization": f"Bearer {cast('dict[str, str]', r.json())['access_token']}"}


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
        return cast("_IdResponse", r.json())["id"]

    def category(self, name: str, group_id: int, keywords: str = "") -> int:
        r = self.client.post(
            "/api/categories", json={"name": name, "groupId": group_id, "keywords": keywords}
        )
        assert r.status_code == 200, r.text
        return cast("_IdResponse", r.json())["id"]

    def account(self, name: str, **kw: object) -> int:
        r = self.client.post("/api/accounts", json={"name": name, **kw})
        assert r.status_code == 200, r.text
        return cast("_IdResponse", r.json())["id"]

    def default_account(self) -> int:
        return self.snapshot()["accounts"][0]["id"]

    def tx(self, date: str, amount: int, **kw: object) -> int:
        kw.setdefault("accountId", self.default_account())
        r = self.client.post("/api/transactions", json={"date": date, "amount": amount, **kw})
        assert r.status_code == 200, r.text
        return cast("_IdResponse", r.json())["id"]

    def transfer(
        self,
        from_account: int,
        to_account: int,
        amount: int,
        date: str = "2026-01-10T12:00:00",
        **kw: object,
    ) -> int:
        r = self.client.post(
            "/api/transfers",
            json={
                "fromAccountId": from_account,
                "toAccountId": to_account,
                "amount": amount,
                "date": date,
                **kw,
            },
        )
        assert r.status_code == 200, r.text
        return cast("_TransferIdResponse", r.json())["transferId"]

    def snapshot(self) -> _Snapshot:
        return cast("_Snapshot", self.client.get("/api/snapshot").json())

    def cat(self, cat_id: int) -> _SnapshotCategory:
        return next(c for c in self.snapshot()["categories"] if c["id"] == cat_id)

    def acct(self, account_id: int) -> _SnapshotAccount:
        return next(a for a in self.snapshot()["accounts"] if a["id"] == account_id)

    def tx_by(self, tx_id: int) -> _SnapshotTransaction:
        return next(t for t in self.snapshot()["transactions"] if t["id"] == tx_id)

    def preview(self, text: str, account_id: int | None = None) -> list[_PreviewRow]:
        body = {"text": text, "accountId": account_id or self.default_account()}
        return cast("_PreviewResponse", self.client.post("/api/import/preview", json=body).json())[
            "rows"
        ]


@pytest.fixture()
def api(client: TestClient) -> Api:
    return Api(client)
