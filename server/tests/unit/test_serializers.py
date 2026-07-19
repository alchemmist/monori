import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from app.deps import (
    serialize_account,
    serialize_budget,
    serialize_category,
    serialize_connection,
    serialize_group,
    serialize_tx,
)

# Distinct sentinel values per field so a key/value mix-up cannot pass by accident.


def test_serialize_group():
    row = {"id": 1, "name": "Bills", "sort": 3, "kind": "expense"}
    assert serialize_group(row) == {"id": 1, "name": "Bills", "sort": 3, "kind": "expense"}


def test_serialize_category():
    row = {
        "id": 7,
        "group_id": 2,
        "name": "Rent",
        "keywords": "rent|landlord",
        "sort": 4,
        "archived": 1,
    }
    assert serialize_category(row) == {
        "id": 7,
        "groupId": 2,
        "name": "Rent",
        "keywords": "rent|landlord",
        "sort": 4,
        "archived": True,
    }


def test_serialize_category_archived_false():
    row = {"id": 7, "group_id": 2, "name": "Rent", "keywords": "", "sort": 4, "archived": 0}
    assert serialize_category(row)["archived"] is False


def test_serialize_account():
    row = {
        "id": 5,
        "name": "T-Bank",
        "type": "card",
        "icon": "wallet",
        "color": "#5b6472",
        "icon_image": None,
        "currency": "RUB",
        "sort": 2,
        "archived": 0,
        "opening_balance": 12345,
        "opening_date": "2024-01-01",
    }
    assert serialize_account(row) == {
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
    }


def test_serialize_account_archived_true():
    row = {
        "id": 5,
        "name": "Old",
        "type": "cash",
        "icon": "sack",
        "color": "#000000",
        "icon_image": "data:image/png;base64,AAAA",
        "currency": "USD",
        "sort": 9,
        "archived": 1,
        "opening_balance": 0,
        "opening_date": None,
    }
    out = serialize_account(row)
    assert out["archived"] is True
    assert out["iconImage"] == "data:image/png;base64,AAAA"


def test_serialize_tx():
    row = {
        "id": 11,
        "date": "2026-01-05T00:00:00",
        "amount": -150000,
        "description": "LANDLORD",
        "bank_category": "Housing",
        "mcc": "6513",
        "category_id": 3,
        "account_id": 1,
        "transfer_id": None,
        "comment": "note",
        "source": "import",
    }
    assert serialize_tx(row) == {
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
    }


def test_serialize_budget():
    row = {"category_id": 3, "year": 2026, "month": 1, "amount": 150000}
    assert serialize_budget(row) == {
        "categoryId": 3,
        "year": 2026,
        "month": 1,
        "amount": 150000,
    }


def test_serialize_connection():
    row = {
        "id": 8,
        "account_id": 2,
        "bank": "tbank",
        "kind": "playwright",
        "status": "connected",
        "last_sync": "2026-02-01T09:00:00",
        "last_error": None,
        "credentials_encrypted": b"cipher",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-02T00:00:00",
    }
    assert serialize_connection(row) == {
        "id": 8,
        "accountId": 2,
        "bank": "tbank",
        "kind": "playwright",
        "status": "connected",
        "lastSync": "2026-02-01T09:00:00",
        "lastError": None,
        "hasCredentials": True,
        "createdAt": "2026-01-01T00:00:00",
        "updatedAt": "2026-01-02T00:00:00",
    }


def test_serialize_connection_without_credentials_and_with_error():
    row = {
        "id": 8,
        "account_id": 2,
        "bank": "tbank",
        "kind": "playwright",
        "status": "error",
        "last_sync": None,
        "last_error": "login rejected",
        "credentials_encrypted": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-02T00:00:00",
    }
    out = serialize_connection(row)
    assert out["hasCredentials"] is False
    assert out["lastError"] == "login rejected"
    assert out["lastSync"] is None
