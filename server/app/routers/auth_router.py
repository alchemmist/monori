"""In-app authentication: register, obtain a token, and read the current user.

This is the skeleton of issue #34 — real accounts that sign in to monori itself.
Per-user data ownership (scoping every table to a user) is a later phase; for now
these endpoints stand up registration and OAuth2 password-grant login, and expose
a ``current_user`` dependency other routes can adopt.
"""

import re
import sqlite3
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from ..auth import current_user
from ..deps import conn, serialize_user
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8


class RegisterBody(BaseModel):
    email: str
    password: str


def _normalize_email(email):
    return email.strip().lower()


@router.post("/register")
def register(body: RegisterBody):
    email = _normalize_email(body.email)
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "invalid email")
    if len(body.password) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"password must be at least {MIN_PASSWORD_LEN} characters")
    c = conn()
    try:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        try:
            cur = c.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, hash_password(body.password), now),
            )
            c.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "email already registered") from None
        uid = cur.lastrowid
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1:
            c.execute("UPDATE accounts SET user_id=? WHERE user_id IS NULL", (uid,))
            c.execute("UPDATE category_groups SET user_id=? WHERE user_id IS NULL", (uid,))
            c.execute("UPDATE bank_connections SET user_id=? WHERE user_id IS NULL", (uid,))
        if not c.execute("SELECT id FROM accounts WHERE user_id=?", (uid,)).fetchone():
            c.execute(
                "INSERT INTO accounts (user_id, name, type, currency, sort)"
                " VALUES (?, 'Cash', 'cash', 'RUB', 1)",
                (uid,),
            )
        c.commit()
        row = c.execute("SELECT id, email, created_at FROM users WHERE id=?", (uid,)).fetchone()
        return serialize_user(row)
    finally:
        c.close()


@router.post("/token")
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """OAuth2 password grant: ``username`` is the email. Returns a bearer token."""
    email = _normalize_email(form.username)
    c = conn()
    try:
        row = c.execute("SELECT id, password_hash FROM users WHERE email=?", (email,)).fetchone()
    finally:
        c.close()
    if row is None or not verify_password(row["password_hash"], form.password):
        raise HTTPException(401, "incorrect email or password")
    return {"access_token": create_access_token(row["id"]), "token_type": "bearer"}


@router.get("/me")
def me(user: Annotated[dict, Depends(current_user)]):
    return user
