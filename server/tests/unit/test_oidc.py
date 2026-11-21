# Copyright (c) 2026
"""Exercise browser transactions against a signed provider response."""

import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from monori.server.app.routers import oidc
from monori.server.tests.conftest import login_as

ISS = "https://id.example/application/o/monori/"
ROOT = "/api/auth/oidc/"


def test_disabled(anon: TestClient) -> None:
    assert anon.get(ROOT + "status").json() == {"enabled": False}
    assert anon.post(ROOT + "start").status_code == 404


def test_oidc_round_trip(anon: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for env_key, value in {
        "ISSUER": ISS,
        "CLIENT_ID": "monori",
        "CLIENT_SECRET": "secret",
        "REDIRECT_URI": "https://budget.example/oidc/callback",
    }.items():
        monkeypatch.setenv("MONORI_OIDC_" + env_key, value)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {
        "iss": ISS,
        "aud": "monori",
        "sub": "person",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "email": "user@example.org",
        "email_verified": True,
    }
    monkeypatch.setattr(
        oidc,
        "discover",
        lambda _: {
            "authorization_endpoint": ISS + "authorize",
            "token_endpoint": ISS + "token",
            "jwks_uri": ISS + "keys",
        },
    )
    monkeypatch.setattr(
        jwt.PyJWKClient,
        "get_signing_key_from_jwt",
        lambda *_: SimpleNamespace(key=key.public_key()),
    )
    monkeypatch.setattr(
        oidc.httpx,
        "post",
        lambda *_args, **_kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", ISS + "token"),
            json={"id_token": jwt.encode(claims, key, algorithm="RS256")},
        ),
    )

    def start(link: str = "", headers: dict[str, str] | None = None) -> dict[str, str]:
        response = anon.post(ROOT + link + "start", headers=headers).json()
        query = parse_qs(urlsplit(response["url"]).query)
        assert query["code_challenge_method"] == ["S256"]
        claims["nonce"] = query["nonce"][0]
        return {"transaction": response["transaction"], "state": query["state"][0], "code": "abc"}

    password_user = login_as(anon, "user@example.org")
    body = start()
    assert anon.post(ROOT + "finish", json={**body, "state": "other"}).status_code == 400
    assert anon.post(ROOT + "finish", json=body).status_code == 409
    claims["nonce"] = "wrong"
    assert anon.post(ROOT + "finish", json=body).status_code == 401
    body = start("link/", password_user)
    assert anon.post(ROOT + "finish", json=body).status_code == 400
    assert anon.post(ROOT + "link/finish", json=body, headers=password_user).status_code == 200
    claims["email"] = "changed@example.org"
    result = anon.post(ROOT + "finish", json=start()).json()
    assert (
        anon.get(
            "/api/auth/me", headers={"Authorization": "Bearer " + result["access_token"]}
        ).json()["email"]
        == "user@example.org"
    )
    claims["sub"] = "another-person"
    result = anon.post(ROOT + "finish", json=start()).json()
    assert (
        anon.get(
            "/api/auth/me", headers={"Authorization": "Bearer " + result["access_token"]}
        ).json()["email"]
        == "changed@example.org"
    )


@pytest.mark.parametrize("field", ["issuer", "token_endpoint"])
def test_discovery_rejects_untrusted_metadata(monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    data = {
        "issuer": ISS,
        "authorization_endpoint": ISS + "authorize",
        "token_endpoint": ISS + "token",
        "jwks_uri": ISS + "keys",
    }
    data[field] = "http://wrong.example/"

    def discovery(url: str) -> httpx.Response:
        assert url == ISS + ".well-known/openid-configuration"
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(oidc.httpx, "get", discovery)
    with pytest.raises(oidc.HTTPException) as error:
        oidc.discover(ISS)
    assert error.value.status_code == 503
