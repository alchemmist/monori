"""Unit tests for the connections router's request models."""

from app.routers.connections import Credentials


def test_credentials_normalize_blank_account_to_none():
    assert Credentials(phone="+7", password="p", account="  5858870594 ").account == "5858870594"
    assert Credentials(phone="+7", password="p", account="   ").account is None
    assert Credentials(phone="+7", password="p", account="").account is None
    assert Credentials(phone="+7", password="p").account is None
