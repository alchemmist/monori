import os
import secrets
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer

from .deps import conn, serialize_user
from .security import decode_access_token


def require_token(authorization: str | None = Header(default=None)):
    token = os.environ.get("MONORI_API_TOKEN")
    if not token:
        return
    expected = f"Bearer {token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "invalid or missing API token")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token", auto_error=True)


def current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    """Resolve the signed-in user from a bearer JWT, or raise 401."""
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as e:
        raise HTTPException(401, "invalid or expired token") from e
    c = conn()
    try:
        row = c.execute("SELECT id, email, created_at FROM users WHERE id=?", (user_id,)).fetchone()
    finally:
        c.close()
    if row is None:
        raise HTTPException(401, "unknown user")
    return serialize_user(row)
