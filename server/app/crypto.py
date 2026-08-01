"""Encryption for bank-connection secrets (credentials and cached sessions).

Secrets are encrypted at rest with a symmetric Fernet key. The key comes from
the ``MONORI_ENCRYPTION_KEY`` environment variable or, if unset, is generated
once and persisted (owner-only) next to the database — so bank connections work
out of the box and survive restarts without any configuration, mirroring the
auth secret. Provide the env var explicitly to share one key across instances or
to rotate it.
"""

import json
import os
import pathlib
from collections.abc import Mapping

from cryptography.fernet import Fernet
from pydantic import JsonValue

from . import db as dbmod
from .connectors.base import JSON_OBJECT_ADAPTER, JsonObject
from .security import load_or_create_secret_file


class CryptoUnavailableError(RuntimeError):
    """Raised when a secret must be handled but no encryption key is configured."""


_key_cache: dict[str, str] = {}


def available() -> bool:
    """Handle available."""
    return True


def generate_key() -> str:
    """Handle generate key."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def _key_path() -> pathlib.Path:
    return pathlib.Path(dbmod.DB_PATH).parent / ".encryption_key"


def _encryption_key() -> str:
    env = os.environ.get("MONORI_ENCRYPTION_KEY")
    if env:
        return env
    path = _key_path()
    key = str(path)
    cached = _key_cache.get(key)
    if cached:
        return cached
    value = load_or_create_secret_file(path, generate_key)
    _key_cache[key] = value
    return value


def _fernet() -> Fernet:
    return Fernet(_encryption_key().encode())


def encrypt(data: Mapping[str, JsonValue]) -> bytes:
    """Encrypt a JSON-serializable dict to an opaque token (bytes)."""
    return _fernet().encrypt(json.dumps(data).encode())


def decrypt(blob: bytes | memoryview | None) -> JsonObject | None:
    """Decrypt a token produced by :func:`encrypt` back to its dict."""
    if blob is None:
        return None
    return JSON_OBJECT_ADAPTER.validate_python(json.loads(_fernet().decrypt(bytes(blob)).decode()))
