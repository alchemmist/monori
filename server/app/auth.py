import os
import secrets

from fastapi import Header, HTTPException


def require_token(authorization: str | None = Header(default=None)):
    token = os.environ.get("MONORI_API_TOKEN")
    if not token:
        return
    expected = f"Bearer {token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "invalid or missing API token")
