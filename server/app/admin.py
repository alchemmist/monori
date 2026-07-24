"""
Admin rights and activity accounting.

Admin rights come from the ``MONORI_ADMIN_EMAILS`` env (comma-separated); the
flag is synced into ``users.is_admin`` at login so the env stays the single
source of truth. Feature usage is counted by an API middleware into per-user
per-feature daily buckets — enough for the admin panel's analytics without
storing a raw request log.
"""

import os
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException

from .auth import current_user
from .deps import conn
from .security import decode_access_token

# usage buckets are keyed by the first path segment after /api; auth is skipped
# because logins are recorded as explicit activity events
UNTRACKED_FEATURES = {"auth"}


def admin_emails():
    raw = os.environ.get("MONORI_ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def admin_user(user: Annotated[dict, Depends(current_user)]):
    if not user.get("isAdmin"):
        raise HTTPException(403, "admin rights required")
    return user


def feature_from_path(path):
    """
    The usage-bucket name for an API path, or None if the request should not be
    counted (non-API paths and ``UNTRACKED_FEATURES``).
    """
    parts = path.split("/")
    if len(parts) < 3 or parts[0] != "" or parts[1] != "api" or not parts[2]:
        return None
    feature = parts[2]
    if feature in UNTRACKED_FEATURES:
        return None
    return feature


def user_id_from_auth_header(header):
    if not header or not header.lower().startswith("bearer "):
        return None
    try:
        return int(decode_access_token(header[7:])["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


def record_api_usage(path, auth_header):
    feature = feature_from_path(path)
    if feature is None:
        return
    uid = user_id_from_auth_header(auth_header)
    if uid is None:
        return
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    c = conn()
    try:
        c.execute(
            "INSERT INTO feature_usage (user_id, feature, day, count) VALUES (?, ?, ?, 1)"
            " ON CONFLICT (user_id, feature, day) DO UPDATE SET count = count + 1",
            (uid, feature, day),
        )
        c.commit()
    finally:
        c.close()
