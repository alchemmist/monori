import pytest

from monori.server.app.connectors.base import ConnectorError
from monori.server.app.connectors.yandex_pay import parse_amount, parse_date, parse_payment_item


def test_parse_amount() -> None:
    assert parse_amount("\N{MINUS SIGN}1 234,50 ₽") == -123450
    assert parse_amount("+99,9 ₽") == 9990


def test_parse_date() -> None:
    assert parse_date("25 августа 2026", year=2020) == "2026-08-25T00:00:00"
    assert parse_date("авг. •• 2026", year=2020) == "2026-08-01T00:00:00"
    assert parse_date("August 23", year=2026) == "2026-08-23T00:00:00"


def test_parse_payment_item() -> None:
    row = parse_payment_item(
        ["Merchant", "\N{MINUS SIGN}1 234,50 ₽"], ["25 августа 2026"], year=2026
    )
    assert row.date == "2026-08-25T00:00:00"
    assert row.amount == -123450
    assert row.description == "Merchant"


def test_parse_payment_item_rejects_missing_fields() -> None:
    with pytest.raises(ConnectorError, match="unexpected structure"):
        parse_payment_item(["Merchant"], ["25 августа 2026"], year=2026)
