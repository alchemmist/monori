# Copyright (c) 2026
"""Confidential OIDC authorization code flow for one configured provider."""

import base64
import hashlib
import os
import secrets
import time
from contextlib import closing
from typing import Annotated
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field
from pydantic.dataclasses import dataclass

from monori.server.app.auth import AuthenticatedUser, current_user
from monori.server.app.db import begin_write
from monori.server.app.deps import conn
from monori.server.app.routers.auth_router import (
    OAuthTokenType,
    TokenResponse,
    create_user,
    record_login,
)
from monori.server.app.security import auth_secret, create_access_token, sso_only_users

router = APIRouter(prefix="/api/auth/oidc", tags=["auth"])
User = Annotated[AuthenticatedUser, Depends(current_user)]
FLOW_AUDIENCE = "monori-oidc-transaction"


@dataclass
class Finish:
    """Browser-held transaction and provider response."""

    transaction: str = Field(max_length=8192)
    code: str = Field(min_length=1, max_length=8192)
    state: str = Field(min_length=1, max_length=256)


def _config() -> tuple[str, str, str, str]:
    issuer, client, secret, redirect = (
        os.getenv("MONORI_OIDC_" + key, "")
        for key in ("ISSUER", "CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI")
    )
    if not all((issuer, client, secret, redirect)):
        raise HTTPException(404, "SSO is not configured")
    return _https(issuer), client, secret, _https(redirect)


def _https(value: str) -> str:
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
        raise HTTPException(503, "Invalid OIDC URL")
    return value


def discover(issuer: str) -> dict[str, str]:
    """Load HTTPS endpoints only from metadata matching the configured issuer."""
    try:
        response = httpx.get(issuer.rstrip("/") + "/.well-known/openid-configuration")
        response.raise_for_status()
        data = response.json()
        if data["issuer"] == issuer:
            return {
                k: _https(data[k]) for k in ("authorization_endpoint", "token_endpoint", "jwks_uri")
            }
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise HTTPException(503, "OIDC discovery unavailable") from exc
    raise HTTPException(503, "Unexpected OIDC issuer")


@router.get("/status")
def status() -> dict[str, bool]:
    """Advertise SSO only when the confidential client is configured."""
    policy = {"ssoOnly": True} if sso_only_users() is not None else {}
    try:
        _config()
    except HTTPException:
        return {"enabled": False, **policy}
    return {"enabled": True, **policy}


def _start(response: Response, uid: int | None) -> dict[str, str]:
    issuer, client, _, redirect = _config()
    meta = discover(issuer)
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    transaction = jwt.encode(
        {
            "aud": FLOW_AUDIENCE,
            "iss": issuer,
            "client": client,
            "uid": uid,
            "state": state,
            "nonce": nonce,
            "verifier": verifier,
            "exp": int(time.time()) + 300,
        },
        auth_secret(),
        algorithm="HS256",
    )
    query = urlencode(
        {
            "client_id": client,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return {"url": meta["authorization_endpoint"] + "?" + query, "transaction": transaction}


@router.post("/start")
def start(response: Response) -> dict[str, str]:
    """Begin a sign-in."""
    return _start(response, None)


@router.post("/link/start")
def link_start(response: Response, user: User) -> dict[str, str]:
    """Bind an explicit linking request to the current local user."""
    if sso_only_users() is not None:
        raise HTTPException(403, "Identity linking is disabled")
    return _start(response, user.id)


def _finish(body: Finish, response: Response, uid: int | None) -> TokenResponse:
    issuer, client, secret, redirect = _config()
    try:
        flow = jwt.decode(
            body.transaction,
            auth_secret(),
            algorithms=["HS256"],
            audience=FLOW_AUDIENCE,
            issuer=issuer,
            options={"require": ["exp", "aud", "iss"]},
        )
        if flow["client"] != client or flow["uid"] != uid or flow["state"] != body.state:
            raise HTTPException(400, "Invalid SSO transaction")
        meta = discover(issuer)
        token = httpx.post(
            meta["token_endpoint"],
            auth=(client, secret),
            data={
                "grant_type": "authorization_code",
                "code": body.code,
                "code_verifier": flow["verifier"],
                "redirect_uri": redirect,
            },
        )
        token.raise_for_status()
        raw = token.json()["id_token"]
        key = jwt.PyJWKClient(meta["jwks_uri"], timeout=5).get_signing_key_from_jwt(raw)
        claims = jwt.decode(
            raw,
            key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=client,
            options={"require": ["sub", "iss", "aud", "exp", "iat", "nonce"]},
        )
        if (
            claims["nonce"] != flow["nonce"]
            or claims.get("azp", client) != client
            or (isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and "azp" not in claims)
            or not isinstance(claims["sub"], str)
            or not claims["sub"]
        ):
            raise HTTPException(401, "Invalid identity token")
    except (jwt.PyJWTError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(401, "SSO verification failed") from exc
    with closing(conn()) as c, c:
        begin_write(c)
        identity = (issuer, claims["sub"])
        row = c.execute(
            "SELECT user_id FROM oidc_identities WHERE issuer=? AND subject=?", identity
        ).fetchone()
        allowed = sso_only_users()
        if allowed is not None and (uid is not None or row is None or str(row[0]) not in allowed):
            raise HTTPException(403, "This identity is not admitted to Monori")
        if row is not None:
            if uid is not None and uid != row[0]:
                raise HTTPException(409, "SSO identity already linked")
            user_id = int(row[0])
        else:
            if uid is None:
                if claims.get("email_verified") is not True or not isinstance(
                    claims.get("email"), str
                ):
                    raise HTTPException(409, "Sign in with a password and link SSO in Settings")
                user_id = create_user(
                    c, claims["email"], secrets.token_urlsafe(48), commit=False
                ).id
            else:
                user_id = uid
            c.execute(
                "INSERT INTO oidc_identities (issuer, subject, user_id) VALUES (?, ?, ?)",
                (*identity, user_id),
            )
        email = c.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()[0]
        record_login(c, user_id, email)
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=create_access_token(user_id, oidc=True), token_type=OAuthTokenType.BEARER
    )


@router.post("/finish")
def finish(body: Finish, response: Response) -> TokenResponse:
    """Exchange a browser-bound authorization response for a Monori session."""
    return _finish(body, response, None)


@router.post("/link/finish")
def link_finish(body: Finish, response: Response, user: User) -> TokenResponse:
    """Require the initiating local account to still be signed in."""
    return _finish(body, response, user.id)
