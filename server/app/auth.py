# Copyright (c) 2026
"""Provide backend functionality."""


from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from monori.server.app.db_records import db_int, db_optional_int, db_optional_str, db_str
from monori.server.app.db_types import DatabaseRow
from monori.server.app.deps import UserResponse, conn
from monori.server.app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token", auto_error=True)


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Represent AuthenticatedUser."""

    id: int
    email: str
    created_at: str
    is_admin: bool
    last_login: str | None
    default_account_id: int | None

    def to_api_dict(self) -> UserResponse:
        """Handle to api dict."""
        return UserResponse(
            id=self.id,
            email=self.email,
            created_at=self.created_at,
            is_admin=self.is_admin,
            last_login=self.last_login,
            default_account_id=self.default_account_id,
        )


def _user_from_row(row: DatabaseRow) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=db_int(row["id"], "id"),
        email=db_str(row["email"], "email"),
        created_at=db_str(row["created_at"], "created_at"),
        is_admin=bool(db_int(row["is_admin"], "is_admin")),
        last_login=db_optional_str(row["last_login"], "last_login"),
        default_account_id=db_optional_int(row["default_account_id"], "default_account_id"),
    )


def current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> AuthenticatedUser:
    """Resolve the signed-in user from a bearer JWT, or raise 401."""
    try:
        payload = decode_access_token(token)
        subject = payload.sub
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
