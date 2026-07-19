"""Password hashing and JWT access tokens for in-app authentication.

Passwords are hashed with Argon2; access tokens are stateless JWTs signed with a
per-instance secret. The secret comes from ``MONORI_AUTH_SECRET`` or, if unset,
is generated once and persisted (owner-only) next to the database so logins
survive restarts without any configuration.
"""

import os
import pathlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

from . import db as dbmod

_hasher = PasswordHasher()

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(days=7)


def hash_password(password):
    return _hasher.hash(password)


def verify_password(password_hash, password):
    try:
        _hasher.verify(password_hash, password)
        return True
    except (Argon2Error, ValueError):
        return False


def _secret_path():
    return pathlib.Path(dbmod.DB_PATH).parent / ".auth_secret"


def auth_secret():
    env = os.environ.get("MONORI_AUTH_SECRET")
    if env:
        return env
    path = _secret_path()
    if path.exists():
        return path.read_text().strip()
    value = secrets.token_hex(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    # write owner-only so the signing key isn't world-readable
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)
    return value


def create_access_token(user_id):
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, auth_secret(), algorithm=ALGORITHM)


def decode_access_token(token):
    """Return the token's payload, or raise jwt.InvalidTokenError."""
    return jwt.decode(token, auth_secret(), algorithms=[ALGORITHM])
