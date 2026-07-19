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


def _use_tmp_db(tmp_path, monkeypatch):
    monkeypatch.delenv("MONORI_AUTH_SECRET", raising=False)
    import app.db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "monori.db"))


def test_auth_secret_persists_owner_only(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    first = security.auth_secret()
    assert first
    # a second call reuses the persisted secret
    assert security.auth_secret() == first
    secret_file = tmp_path / ".auth_secret"
    assert secret_file.exists()
    assert (secret_file.stat().st_mode & 0o077) == 0  # not group/world readable


def test_auth_secret_is_cached_in_memory(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    first = security.auth_secret()
    (tmp_path / ".auth_secret").unlink()
    assert security.auth_secret() == first


def test_auth_secret_fixes_loose_permissions(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    secret_file = tmp_path / ".auth_secret"
    secret_file.write_text("preexisting-secret")
    secret_file.chmod(0o644)
    assert security.auth_secret() == "preexisting-secret"
    assert (secret_file.stat().st_mode & 0o077) == 0


def test_auth_secret_regenerates_empty_file(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    secret_file = tmp_path / ".auth_secret"
    secret_file.write_text("")
    value = security.auth_secret()
    assert value
    assert secret_file.read_text().strip() == value


def test_auth_secret_generates_64_hex_chars(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    value = security.auth_secret()
    assert len(value) == 64
    int(value, 16)


def test_auth_secret_creates_missing_parent_dirs(tmp_path, monkeypatch):
    monkeypatch.delenv("MONORI_AUTH_SECRET", raising=False)
    import app.db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "a" / "b" / "monori.db"))
    value = security.auth_secret()
    assert (tmp_path / "a" / "b" / ".auth_secret").read_text().strip() == value


def test_auth_secret_leaves_tight_permissions_untouched(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    secret_file = tmp_path / ".auth_secret"
    secret_file.write_text("already-tight")
    secret_file.chmod(0o600)
    calls = []
    original = pathlib.Path.chmod

    def spy(self, mode, **kwargs):
        calls.append(mode)
        return original(self, mode, **kwargs)

    monkeypatch.setattr(pathlib.Path, "chmod", spy)
    assert security.auth_secret() == "already-tight"
    assert calls == []


def test_auth_secret_lost_create_race_reads_winner(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    secret_file = tmp_path / ".auth_secret"

    def lose_race(*args, **kwargs):
        secret_file.write_text("winner-secret")
        raise FileExistsError

    monkeypatch.setattr(security.os, "open", lose_race)
    assert security.auth_secret() == "winner-secret"
