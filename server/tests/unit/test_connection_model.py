"""
Unit tests for the connections router's credential validation and the
connector registry's parameter declarations.
"""

import pytest
from fastapi import HTTPException

import app.connectors.fake  # noqa: F401
from app.connectors.base import available_connectors
from app.routers.connections import _validate_credentials


def test_validate_credentials_requires_declared_fields():
    with pytest.raises(HTTPException) as e:
        _validate_credentials("tbank", "playwright", {"phone": "+7"})
    assert e.value.status_code == 400
    assert "password" in e.value.detail


def test_validate_credentials_rejects_blank_required():
    with pytest.raises(HTTPException) as e:
        _validate_credentials("tbank", "playwright", {"phone": "  ", "password": "p"})
    assert "phone" in e.value.detail


def test_validate_credentials_accepts_complete_set():
    _validate_credentials("tbank", "playwright", {"phone": "+7", "password": "p"})


def test_validate_credentials_unknown_connector():
    with pytest.raises(HTTPException) as e:
        _validate_credentials("nope", "nope", {})
    assert e.value.status_code == 400


def test_available_connectors_declare_params_and_hide_fake():
    conns = available_connectors()
    banks = {c["bank"] for c in conns}
    assert "fake" not in banks
    tbank = next(c for c in conns if c["bank"] == "tbank")
    assert tbank["label"]
    names = {p["name"] for p in tbank["connectionParams"]}
    assert {"phone", "password"} <= names
    secret = {p["name"]: p["secret"] for p in tbank["connectionParams"]}
    assert secret["password"] is True
    assert [p["name"] for p in tbank["accountParams"]] == ["account"]
