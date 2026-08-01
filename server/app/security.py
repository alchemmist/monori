"""Password hashing and JWT access tokens for in-app authentication.

Passwords are hashed with Argon2; access tokens are stateless JWTs signed with a
per-instance secret. The secret comes from ``MONORI_AUTH_SECRET`` or, if unset,
is generated once and persisted (owner-only) next to the database so logins
survive restarts without any configuration.
"""

import os
import pathlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from pydantic import ConfigDict, TypeAdapter
from pydantic.dataclasses import dataclass as pydantic_dataclass

from . import db as dbmod

_hasher = PasswordHasher()

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(days=7)


@pydantic_dataclass(config=ConfigDict(extra="ignore"))
class TokenPayload:
    """Represent TokenPayload."""

    sub: str
    iat: int
    exp: int


TOKEN_PAYLOAD_ADAPTER: TypeAdapter[TokenPayload] = TypeAdapter(TokenPayload)


def hash_password(password: str) -> str:
    """Handle hash password."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Handle verify password."""
    try:
        _hasher.verify(password_hash, password)
        return True  # noqa: TRY300
    except (Argon2Error, ValueError):
        return False


def _secret_path() -> pathlib.Path:
    return pathlib.Path(dbmod.DB_PATH).parent / ".auth_secret"


_secret_cache: dict[str, str] = {}


def auth_secret() -> str:
    """Handle auth secret."""
    env = os.environ.get("MONORI_AUTH_SECRET")
    if env:
        return env
    path = _secret_path()
    key = str(path)
    cached = _secret_cache.get(key)
    if cached:
        return cached
    value = _load_or_create_secret(path)
    _secret_cache[key] = value
    return value


def _load_or_create_secret(path: pathlib.Path) -> str:
    return load_or_create_secret_file(path, lambda: secrets.token_hex(32))


def load_or_create_secret_file(path: pathlib.Path, generate: Callable[[], str]) -> str:
    """Read a secret from ``path``; if it is missing or empty, generate one with.

    ``generate()`` and persist it owner-only. Concurrency-safe via exclusive.
    create — concurrent workers that lose the race read the winner's value.
    """
    if path.exists():
        existing = path.read_text().strip()
        if existing:
            if path.stat().st_mode & 0o077:
                path.chmod(0o600)
            return existing
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = generate()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text().strip()
    with os.fdopen(fd, "w") as f:
        f.write(value)
    return value


def create_access_token(user_id: int) -> str:
    """Handle create access token."""
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, auth_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    """Return the token's payload, or raise jwt.InvalidTokenError."""
    return TOKEN_PAYLOAD_ADAPTER.validate_python(
        jwt.decode(token, auth_secret(), algorithms=[ALGORITHM]),
    )
