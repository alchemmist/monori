from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from .deps import conn, serialize_user
from .security import decode_access_token

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
