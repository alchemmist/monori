"""
In-app authentication: register, obtain a token, and read the current user.

This is the skeleton of issue #34 — real accounts that sign in to monori itself.
Per-user data ownership (scoping every table to a user) is a later phase; for now
these endpoints stand up registration and OAuth2 password-grant login, and expose
a ``current_user`` dependency other routes can adopt.
"""

import sqlite3
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from ..admin import admin_emails
from ..auth import current_user
from ..deps import conn, serialize_user
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

MIN_PASSWORD_LEN = 8
MAX_EMAIL_LEN = 254


def _valid_email(email):
    """
    Shape check for an email: one ``@``, non-empty local part, and a dotted
    domain with no empty labels. Linear and non-backtracking (bounded by
    ``MAX_EMAIL_LEN``) so it cannot be driven into a ReDoS.
    """
    if not email or len(email) > MAX_EMAIL_LEN or any(ch.isspace() for ch in email):
        return False
    local, sep, domain = email.partition("@")
    if not sep or not local or "@" in domain or "." not in domain:
        return False
    return all(domain.split("."))


class RegisterBody(BaseModel):
    email: str
    password: str


def _normalize_email(email):
    return email.strip().lower()


def create_user(c, raw_email, password):
    """
    Validate and insert a user (with a default Cash account), returning the
    serialized user. Shared by public registration and admin user creation.
    Raises HTTPException on invalid input or duplicate email.
    """
    email = _normalize_email(raw_email)
    if not _valid_email(email):
        raise HTTPException(400, "invalid email")
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"password must be at least {MIN_PASSWORD_LEN} characters")
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        cur = c.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, hash_password(password), now),
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
    row = c.execute(
        "SELECT id, email, created_at, is_admin, last_login FROM users WHERE id=?", (uid,)
    ).fetchone()
    return serialize_user(row)


@router.post("/register")
def register(body: RegisterBody):
    c = conn()
    try:
        return create_user(c, body.email, body.password)
    finally:
        c.close()


@router.post("/token")
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """
    OAuth2 password grant: ``username`` is the email. Returns a bearer token.
    """
    email = _normalize_email(form.username)
    c = conn()
    try:
        row = c.execute("SELECT id, password_hash FROM users WHERE email=?", (email,)).fetchone()
        if row is None or not verify_password(row["password_hash"], form.password):
            raise HTTPException(401, "incorrect email or password")
        # MONORI_ADMIN_EMAILS is the source of truth for admin rights, so the
        # flag is (re)synced on every successful login
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        c.execute(
            "UPDATE users SET is_admin=?, last_login=? WHERE id=?",
            (1 if email in admin_emails() else 0, now, row["id"]),
        )
        c.execute(
            "INSERT INTO activity_events (user_id, kind, created_at) VALUES (?, 'login', ?)",
            (row["id"], now),
        )
        c.commit()
    finally:
        c.close()
    return {"access_token": create_access_token(row["id"]), "token_type": "bearer"}


@router.get("/me")
def me(user: Annotated[dict, Depends(current_user)]):
    return user
