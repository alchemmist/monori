from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import app.db as dbmod
from app import crypto


def _use_tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONORI_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "monori.db"))
    crypto.clear_key_cache()


def test_round_trip_with_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONORI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert crypto.available() is True
    secret = {"phone": "+70000000000", "password": "hunter2"}
    blob = crypto.encrypt(secret)
    assert isinstance(blob, bytes)
    assert b"hunter2" not in blob
    assert crypto.decrypt(blob) == secret


def test_decrypt_none_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONORI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert crypto.decrypt(None) is None


def test_generate_key_is_usable(monkeypatch: pytest.MonkeyPatch) -> None:
    key = crypto.generate_key()
    monkeypatch.setenv("MONORI_ENCRYPTION_KEY", key)
    assert crypto.decrypt(crypto.encrypt({"x": 2})) == {"x": 2}


def test_auto_provisions_key_without_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_tmp_db(tmp_path, monkeypatch)
    assert crypto.available() is True
    blob = crypto.encrypt({"a": 1})
    assert crypto.decrypt(blob) == {"a": 1}
    key_file = tmp_path / ".encryption_key"
    assert key_file.exists()
    assert (key_file.stat().st_mode & 0o077) == 0


def test_persisted_key_survives_fresh_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_tmp_db(tmp_path, monkeypatch)
    blob = crypto.encrypt({"a": 1})
    crypto.clear_key_cache()
    assert crypto.decrypt(blob) == {"a": 1}


def test_env_key_takes_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setenv("MONORI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    crypto.encrypt({"a": 1})
    assert not (tmp_path / ".encryption_key").exists()
