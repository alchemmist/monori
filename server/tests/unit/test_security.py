import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import jwt
import pytest

from app import security


def test_hash_and_verify_password():
    h = security.hash_password("correct horse")
    assert h != "correct horse"
    assert security.verify_password(h, "correct horse") is True
    assert security.verify_password(h, "wrong") is False


def test_verify_rejects_garbage_hash():
    assert security.verify_password("not-a-hash", "anything") is False


def test_access_token_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("MONORI_AUTH_SECRET", "x" * 40)
    token = security.create_access_token(42)
    payload = security.decode_access_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload


def test_decode_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("MONORI_AUTH_SECRET", "a" * 40)
    token = security.create_access_token(1)
    monkeypatch.setenv("MONORI_AUTH_SECRET", "b" * 40)
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_access_token(token)


def test_auth_secret_persists_owner_only(tmp_path, monkeypatch):
    monkeypatch.delenv("MONORI_AUTH_SECRET", raising=False)
    import app.db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "monori.db"))
    first = security.auth_secret()
    assert first
    # a second call reuses the persisted secret
    assert security.auth_secret() == first
    secret_file = tmp_path / ".auth_secret"
    assert secret_file.exists()
    assert (secret_file.stat().st_mode & 0o077) == 0  # not group/world readable
