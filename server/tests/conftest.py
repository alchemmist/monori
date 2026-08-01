import os
import pathlib
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from app.main import app as fastapi_app

import app.db as dbmod

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.deps import (
    AccountResponse,
    CategoryResponse,
    IdResponse,
    SnapshotResponse,
    TransactionResponse,
)
from app.routers.auth_router import TokenResponse
from app.routers.imports import ImportPreviewResponse, ImportRowResponse
from app.routers.transfers import TransferIdResponse

STATEMENT = (
    "05.01.2026 10:00:00\t05.01.2026\t*1\tOK\t-100,00\tRUB\t-100,00\tRUB\t\t"
    "Super\t5411\tLenta\t0\t0\t-100,00\n"
    "06.01.2026 11:00:00\t06.01.2026\t*1\tOK\t-200,00\tRUB\t-200,00\tRUB\t\t"
    "Super\t5411\tOkey\t0\t0\t-200,00\n"
)


def _fresh_app_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    monkeypatch.setenv("MONORI_DB", db_path)

    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
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
        *,
        account_type: str = "cash",
        icon: str = "wallet",
        color: str = "#5b6472",
        currency: str = "RUB",
        opening_balance: int = 0,
        bank_ref: str = "",
        card_tails: list[str] | None = None,
        **legacy_kwargs: object,
    ) -> int:
        if "type" in legacy_kwargs:
            account_type = legacy_kwargs.pop("type")
            if not isinstance(account_type, str):
                raise TypeError
        if "openingBalance" in legacy_kwargs:
            opening_balance = legacy_kwargs.pop("openingBalance")
            if not isinstance(opening_balance, int):
                raise TypeError
        if "bankRef" in legacy_kwargs:
            bank_ref = legacy_kwargs.pop("bankRef")
            if not isinstance(bank_ref, str):
                raise TypeError
        if "cardTails" in legacy_kwargs:
            card_tails = legacy_kwargs.pop("cardTails")
            if not isinstance(card_tails, list) and card_tails is not None:
                raise TypeError
        if legacy_kwargs:
            raise TypeError
        body = {
            "name": name,
            "type": account_type,
            "icon": icon,
            "color": color,
            "currency": currency,
            "openingBalance": opening_balance,
            "bankRef": bank_ref,
            "cardTails": card_tails or [],
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
        *,
        account_id: int | None = None,
        category_id: int | None = None,
        description: str = "",
        bank_category: str = "",
        mcc: str = "",
        comment: str = "",
        **legacy_kwargs: object,
    ) -> int:
        if "accountId" in legacy_kwargs:
            account_id = legacy_kwargs.pop("accountId")

        if "categoryId" in legacy_kwargs:
            category_id = legacy_kwargs.pop("categoryId")

        if "bankCategory" in legacy_kwargs:
            bank_category = legacy_kwargs.pop("bankCategory")

        if legacy_kwargs:
            raise TypeError

        r = self.client.post(
            "/api/transactions",
            json={
                "date": date,
                "amount": amount,
                "accountId": account_id or self.default_account(),
                "categoryId": category_id,
                "description": description,
                "bankCategory": bank_category,
                "mcc": mcc,
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
