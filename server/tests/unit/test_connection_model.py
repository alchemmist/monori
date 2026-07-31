"""
Unit tests for the connections router's credential validation and the
connector registry's parameter declarations.
"""

from typing import cast

import pytest
from fastapi import HTTPException

import app.connectors.fake  # noqa: F401
from app.connectors.base import available_connectors
from app.routers.connections import _validate_credentials


def test_validate_credentials_requires_declared_fields() -> None:
    with pytest.raises(HTTPException) as e:
        _validate_credentials("tbank", "playwright", {"phone": "+7"})
    assert e.value.status_code == 400
    assert "password" in e.value.detail


def test_validate_credentials_rejects_blank_required() -> None:
    with pytest.raises(HTTPException) as e:
        _validate_credentials("tbank", "playwright", {"phone": "  ", "password": "p"})
    assert "phone" in e.value.detail


def test_validate_credentials_accepts_complete_set() -> None:
    _validate_credentials("tbank", "playwright", {"phone": "+7", "password": "p"})


def test_validate_credentials_unknown_connector() -> None:
    with pytest.raises(HTTPException) as e:
        _validate_credentials("nope", "nope", {})
    assert e.value.status_code == 400


def test_available_connectors_declare_params_and_hide_fake() -> None:
    conns = available_connectors()
    banks = {c["bank"] for c in conns}
    assert "fake" not in banks
    tbank = next(c for c in conns if c["bank"] == "tbank")
    assert tbank["label"]
    connection_params = cast("list[dict[str, object]]", tbank["connectionParams"])
    names = {p["name"] for p in connection_params}
    assert {"phone", "password"} <= names
    secret = {p["name"]: p["secret"] for p in connection_params}
    assert secret["password"] is True
    account_params = cast("list[dict[str, object]]", tbank["accountParams"])
    assert [p["name"] for p in account_params] == ["account"]
