import pathlib
import sys
from dataclasses import asdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from app.db_records import (
    AccountRecord,
    BudgetRecord,
    CategoryRecord,
    ConnectionRecord,
    GroupRecord,
    TransactionRecord,
)
from app.deps import (
    serialize_account,
    serialize_budget,
    serialize_category,
    serialize_connection,
    serialize_group,
    serialize_tx,
)


def test_serialize_group() -> None:
    row = GroupRecord(id=1, name="Bills", sort=3, kind="expense")
    assert asdict(serialize_group(row)) == {
        "id": 1,
        "name": "Bills",
        "sort": 3,
        "kind": "expense",
    }


def test_serialize_category() -> None:
    row = CategoryRecord(
        id=7,
        group_id=2,
        name="Rent",
        keywords="rent|landlord",
        sort=4,
        archived=True,
    )
    assert asdict(serialize_category(row)) == {
        "id": 7,
        "groupId": 2,
        "name": "Rent",
        "keywords": "rent|landlord",
        "sort": 4,
        "archived": True,
        "goalTarget": None,
        "goalStatus": None,
        "goalTargetDate": None,
    }


def test_serialize_category_archived_false() -> None:
    row = CategoryRecord(id=7, group_id=2, name="Rent", keywords="", sort=4, archived=False)
    assert serialize_category(row).archived is False


def test_serialize_account() -> None:
    row = AccountRecord(
        id=5,
        name="T-Bank",
        type="card",
        icon="wallet",
        color="#5b6472",
        icon_image=None,
        currency="RUB",
        sort=2,
        archived=False,
        opening_balance=12345,
        opening_date="2024-01-01",
        connection_id=9,
        bank_ref="5858870594",
        card_tails="8181,2947",
    )
    assert asdict(serialize_account(row)) == {
        "id": 5,
        "name": "T-Bank",
        "type": "card",
        "icon": "wallet",
        "color": "#5b6472",
        "iconImage": None,
        "currency": "RUB",
        "sort": 2,
        "archived": False,
        "openingBalance": 12345,
        "openingDate": "2024-01-01",
        "connectionId": 9,
        "bankRef": "5858870594",
        "cardTails": ["8181", "2947"],
    }


def test_serialize_account_archived_true() -> None:
    row = AccountRecord(
        id=5,
        name="Old",
        type="cash",
        icon="sack",
        color="#000000",
        icon_image="data:image/png;base64,AAAA",
        currency="USD",
        sort=9,
        archived=True,
        opening_balance=0,
        opening_date=None,
        connection_id=None,
        bank_ref="",
        card_tails="",
    )
    out = serialize_account(row)
    assert out.archived is True
    assert out.iconImage == "data:image/png;base64,AAAA"


def test_serialize_tx() -> None:
    row = TransactionRecord(
        id=11,
        date="2026-01-05T00:00:00",
        amount=-150000,
        description="LANDLORD",
        bank_category="Housing",
        mcc="6513",
        category_id=3,
        account_id=1,
        transfer_id=None,
        comment="note",
        source="import",
        hidden=False,
    )
    assert asdict(serialize_tx(row)) == {
        "id": 11,
        "date": "2026-01-05T00:00:00",
        "amount": -150000,
        "description": "LANDLORD",
        "bankCategory": "Housing",
        "mcc": "6513",
        "categoryId": 3,
        "accountId": 1,
        "transferId": None,
        "comment": "note",
        "source": "import",
        "hidden": False,
        "splits": [],
    }


def test_serialize_budget() -> None:
    row = BudgetRecord(category_id=3, year=2026, month=1, amount=150000)
    assert asdict(serialize_budget(row)) == {
        "categoryId": 3,
        "year": 2026,
        "month": 1,
        "amount": 150000,
    }


def test_serialize_connection() -> None:
    row = ConnectionRecord(
        id=8,
        bank="tbank",
        kind="playwright",
        status="connected",
        last_sync="2026-02-01T09:00:00",
        last_error=None,
        has_credentials=True,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-02T00:00:00",
    )
    assert asdict(serialize_connection(row)) == {
        "id": 8,
        "bank": "tbank",
        "kind": "playwright",
        "status": "connected",
        "lastSync": "2026-02-01T09:00:00",
        "lastError": None,
        "hasCredentials": True,
        "createdAt": "2026-01-01T00:00:00",
        "updatedAt": "2026-01-02T00:00:00",
    }


def test_serialize_connection_without_credentials_and_with_error() -> None:
    row = ConnectionRecord(
        id=8,
        bank="tbank",
        kind="playwright",
        status="error",
        last_sync=None,
        last_error="login rejected",
        has_credentials=False,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-02T00:00:00",
    )
    out = serialize_connection(row)
    assert out.hasCredentials is False
    assert out.lastError == "login rejected"
    assert out.lastSync is None
