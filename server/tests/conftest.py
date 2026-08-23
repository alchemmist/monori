import pathlib
import sys
import tempfile
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

import monori.server.app.db as dbmod
from monori.server.app.deps import (
    AccountResponse,
    CategoryResponse,
    IdResponse,
    SnapshotResponse,
    TransactionResponse,
)
from monori.server.app.main import app as fastapi_app
from monori.server.app.routers.auth_router import TokenResponse
from monori.server.app.routers.imports import ImportPreviewResponse, ImportRowResponse
from monori.server.app.routers.transfers import TransferIdResponse

STATEMENT = (
    "05.01.2026 10:00:00\t05.01.2026\t*1\tOK\t-100,00\tRUB\t-100,00\tRUB\t\t"
    "Super\t5411\tLenta\t0\t0\t-100,00\n"
    "06.01.2026 11:00:00\t06.01.2026\t*1\tOK\t-200,00\tRUB\t-200,00\tRUB\t\t"
    "Super\t5411\tOkey\t0\t0\t-200,00\n"
)


@dataclass(frozen=True)
class AccountOptions:
    account_type: str = "cash"
    icon: str = "wallet"
    color: str = "#5b6472"
    currency: str = "RUB"
    opening_balance: int = 0
    bank_ref: str = ""
    card_tails: list[str] | None = None


@dataclass(frozen=True)
class TransactionOptions:
    account_id: int | None = None
    category_id: int | None = None
    description: str = ""
    bank_category: str = ""
    mcc: str = ""
    comment: str = ""


def _fresh_app_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = pathlib.Path(tempfile.mkdtemp()) / "test.db"
    monkeypatch.setenv("MONORI_DB", str(db_path))

    monkeypatch.setattr(dbmod, "DB_PATH", str(db_path))
    dbmod.connect(db_path).close()

    return TestClient(fastapi_app)


def login_as(client: TestClient, email: str, password: str = "hunter2pw") -> dict[str, str]:
    """Register (if needed) and sign in; returns a bearer-token header dict."""
    client.post("/api/auth/register", json={"email": email, "password": password})
    r = client.post("/api/auth/token", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    token = TypeAdapter(TokenResponse).validate_python(r.json())
    return {"Authorization": f"Bearer {token.access_token}"}


def _response_id(response: IdResponse) -> int:
    assert response.id is not None
    return response.id


@pytest.fixture
def anon(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Handle A client with no credentials attached (the DB is fresh and empty)."""
    return _fresh_app_client(monkeypatch)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    Handle A client signed in as the default test user; every request carries the.

    bearer token via default headers.
    """
    c = _fresh_app_client(monkeypatch)
    c.headers.update(login_as(c, "tester@example.com"))
    return c


class Api:
    """
    Thin helper over the HTTP client for arranging test state. Bodies that.

    should always succeed assert 200; error paths are exercised with the raw.
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
            "/api/categories",
            json={"name": name, "groupId": group_id, "keywords": keywords},
        )
        assert r.status_code == 200, r.text
        return _response_id(TypeAdapter(IdResponse).validate_python(r.json()))

    def account(
        self,
        name: str,
        options: AccountOptions | None = None,
    ) -> int:
        options = options or AccountOptions()
        body = {
            "name": name,
            "type": options.account_type,
            "icon": options.icon,
            "color": options.color,
            "currency": options.currency,
            "openingBalance": options.opening_balance,
            "bankRef": options.bank_ref,
            "cardTails": options.card_tails or [],
        }
        r = self.client.post("/api/accounts", json=body)
        assert r.status_code == 200, r.text
        return _response_id(TypeAdapter(IdResponse).validate_python(r.json()))

    def default_account(self) -> int:
        return self.snapshot().accounts[0].id

    def tx(
        self,
        date: str,
        amount: int,
        options: TransactionOptions | None = None,
    ) -> int:
        options = options or TransactionOptions()
        r = self.client.post(
            "/api/transactions",
            json={
                "date": date,
                "amount": amount,
                "accountId": options.account_id or self.default_account(),
                "categoryId": options.category_id,
                "description": options.description,
                "bankCategory": options.bank_category,
                "mcc": options.mcc,
                "comment": options.comment,
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
        return TypeAdapter(TransferIdResponse).validate_python(r.json()).transfer_id

    def snapshot(self) -> SnapshotResponse:
        return TypeAdapter(SnapshotResponse).validate_python(
            self.client.get("/api/snapshot").json(),
        )

    def cat(self, cat_id: int) -> CategoryResponse:
        return next(category for category in self.snapshot().categories if category.id == cat_id)

    def acct(self, account_id: int) -> AccountResponse:
        return next(account for account in self.snapshot().accounts if account.id == account_id)

    def tx_by(self, tx_id: int) -> TransactionResponse:
        return next(
            transaction for transaction in self.snapshot().transactions if transaction.id == tx_id
        )

    def preview(self, text: str, account_id: int | None = None) -> list[ImportRowResponse]:
        body = {"text": text, "accountId": account_id or self.default_account()}
        response = self.client.post("/api/import/preview", json=body)
        return TypeAdapter(ImportPreviewResponse).validate_python(response.json()).rows


@pytest.fixture
def api(client: TestClient) -> Api:
    return Api(client)
