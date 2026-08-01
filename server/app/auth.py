import sqlite3
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from .deps import UserResponse, conn
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token", auto_error=True)


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: int
    email: str
    created_at: str
    is_admin: bool
    last_login: str | None
    default_account_id: int | None

    def to_api_dict(self) -> UserResponse:
        return UserResponse(
            id=self.id,
            email=self.email,
            createdAt=self.created_at,
            isAdmin=self.is_admin,
            lastLogin=self.last_login,
            defaultAccountId=self.default_account_id,
        )


def _user_from_row(row: sqlite3.Row) -> AuthenticatedUser:
    last_login = row["last_login"]
    default_account_id = row["default_account_id"]
    return AuthenticatedUser(
        id=int(row["id"]),
        email=str(row["email"]),
        created_at=str(row["created_at"]),
        is_admin=bool(row["is_admin"]),
        last_login=last_login if isinstance(last_login, str) else None,
        default_account_id=default_account_id if isinstance(default_account_id, int) else None,
    )


def current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> AuthenticatedUser:
    """
    Resolve the signed-in user from a bearer JWT, or raise 401.
    """
    try:
        payload = decode_access_token(token)
        subject = payload["sub"]
        if not isinstance(subject, str):
            raise ValueError("token subject is not a string")
        user_id = int(subject)
    except (jwt.InvalidTokenError, KeyError, ValueError) as e:
        raise HTTPException(401, "invalid or expired token") from e
    c = conn()
    try:
        row = c.execute(
            "SELECT id, email, created_at, is_admin, last_login, default_account_id"
            " FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    finally:
        c.close()
    if row is None:
        raise HTTPException(401, "unknown user")
    return _user_from_row(row)
