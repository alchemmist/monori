import pytest
from cryptography.fernet import Fernet

from app import crypto


def test_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("MONORI_ENCRYPTION_KEY", raising=False)
    assert crypto.available() is False
    with pytest.raises(crypto.CryptoUnavailable):
        crypto.encrypt({"a": 1})


def test_round_trip(monkeypatch):
    monkeypatch.setenv("MONORI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert crypto.available() is True
    secret = {"phone": "+70000000000", "password": "hunter2"}
    blob = crypto.encrypt(secret)
    assert isinstance(blob, bytes)
    assert b"hunter2" not in blob
    assert crypto.decrypt(blob) == secret


def test_decrypt_none_is_none(monkeypatch):
    monkeypatch.setenv("MONORI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert crypto.decrypt(None) is None


def test_generate_key_is_usable(monkeypatch):
    key = crypto.generate_key()
    monkeypatch.setenv("MONORI_ENCRYPTION_KEY", key)
    assert crypto.decrypt(crypto.encrypt({"x": 2})) == {"x": 2}
