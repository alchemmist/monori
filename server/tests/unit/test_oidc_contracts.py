# Copyright (c) 2026
"""
Unit tests pinning the OIDC protocol contracts inside the SSO flow.

The mutation gate runs only unit tests, and the previous round-trip test
stubbed the IdP with ``lambda *_args, **_kwargs: ...``: any change to the
authorization URL parameters, the token exchange request or the JWKS client
setup passed unnoticed. These tests pin those wire contracts, the
multi-audience ``azp`` rules, the unverified-email policy and the
already-linked conflict status.
"""

import base64
import hashlib
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

ISS = "https://sso.example.org/"
ROOT = "/api/auth/oidc/"
META = {
    "authorization_endpoint": ISS + "authorize",
    "token_endpoint": ISS + "token",
    "jwks_uri": ISS + "keys",
}
CLIENT = "monori"
SECRET = "secret"
REDIRECT = "https://budget.example/oidc/callback"


@pytest.fixture
def sso(anon: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict:
    for env_key, value in {
        "ISSUER": ISS,
        "CLIENT_ID": CLIENT,
        "CLIENT_SECRET": SECRET,
        "REDIRECT_URI": REDIRECT,
    }.items():
        monkeypatch.setenv("MONORI_OIDC_" + env_key, value)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    captured: dict = {"posts": [], "post_fails": False, "discovers": [], "signing_keys": []}

    def post(
        url: str, *, auth: tuple[str, str] | None = None, data: dict[str, str] | None = None
    ) -> httpx.Response:
        captured["posts"].append((url, (), {"auth": auth, "data": data}))
        if captured["post_fails"]:
            return httpx.Response(503, request=httpx.Request("POST", url), json={"error": "down"})
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"id_token": captured["id_token"]},
        )

    class RecordingJWKClient(jwt.PyJWKClient):
        def __init__(self, uri: str, timeout: int | None = None) -> None:
            captured["jwk"] = (uri, timeout)
            super().__init__(uri, timeout=timeout)

    monkeypatch.setattr(
        oidc, "discover", lambda issuer: captured["discovers"].append(issuer) or META
    )
    monkeypatch.setattr(oidc.httpx, "post", post)
    monkeypatch.setattr(oidc.jwt, "PyJWKClient", RecordingJWKClient)
    monkeypatch.setattr(
        jwt.PyJWKClient,
        "get_signing_key_from_jwt",
        lambda _, raw: (
            captured["signing_keys"].append(raw) or SimpleNamespace(key=key.public_key())
        ),
    )
    return {"client": anon, "key": key, "captured": captured}


def _start(sso: dict) -> dict:
    response = sso["client"].post(ROOT + "start")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    url = response.json()["url"]
    query = parse_qs(urlsplit(url).query)
    return {
        "transaction": response.json()["transaction"],
        "state": query["state"][0],
        "nonce": query["nonce"][0],
        "query": query,
        "url": url,
    }


def _finish(sso: dict, claims_extra: dict | None = None) -> httpx.Response:
    start = _start(sso)
    verifier = jwt.decode(start["transaction"], key="", options={"verify_signature": False})[
        "verifier"
    ]
    claims = {
        "iss": ISS,
        "aud": CLIENT,
        "sub": "person",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "nonce": start["nonce"],
        "email": "user@example.org",
        "email_verified": True,
    }
    claims.update(claims_extra or {})
    sso["captured"]["id_token"] = jwt.encode(claims, sso["key"], algorithm="RS256")
    response = sso["client"].post(
        ROOT + "finish",
        json={
            "transaction": start["transaction"],
            "state": start["state"],
            "code": "abc",
        },
    )
    sso["captured"]["verifier"] = verifier
    return response


def test_start_url_carries_the_oauth2_wire_contract(sso: dict) -> None:
    start = _start(sso)
    assert sso["captured"]["discovers"] == [ISS]
    assert start["url"].startswith(META["authorization_endpoint"] + "?")
    assert set(start["query"]) == {
        "client_id",
        "redirect_uri",
        "response_type",
        "scope",
        "state",
        "nonce",
        "code_challenge",
        "code_challenge_method",
    }
    assert start["query"]["client_id"] == [CLIENT]
    assert start["query"]["redirect_uri"] == [REDIRECT]
    assert start["query"]["response_type"] == ["code"]
    assert start["query"]["scope"] == ["openid profile email"]
    assert start["query"]["code_challenge_method"] == ["S256"]
    verifier = jwt.decode(start["transaction"], key="", options={"verify_signature": False})[
        "verifier"
    ]
    assert set(verifier) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert start["query"]["code_challenge"] == [expected]
    # state and nonce: 32 random bytes, base64url-encoded without padding.
    assert len(start["query"]["nonce"][0]) == 43
    assert set(start["query"]["state"][0]) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )


def test_finish_exchanges_the_code_with_the_idp_contract(sso: dict) -> None:
    flow = _finish(sso)
    assert flow.status_code == 200
    assert flow.headers["cache-control"] == "no-store"
    assert sso["captured"]["discovers"] == [ISS, ISS]  # start + finish
    assert len(sso["captured"]["signing_keys"]) == 1
    assert (
        jwt.decode(
            sso["captured"]["signing_keys"][0],
            key="",
            options={"verify_signature": False},
        )["sub"]
        == "person"
    )
    posts = sso["captured"]["posts"]
    assert len(posts) == 1
    url, _args, kwargs = posts[0]
    assert url == META["token_endpoint"]
    assert kwargs["auth"] == (CLIENT, SECRET)
    assert kwargs["data"] == {
        "grant_type": "authorization_code",
        "code": "abc",
        "code_verifier": sso["captured"]["verifier"],
        "redirect_uri": REDIRECT,
    }
    assert sso["captured"]["jwk"] == (META["jwks_uri"], 5)


def test_single_audience_list_needs_no_azp(sso: dict) -> None:
    assert _finish(sso, {"aud": [CLIENT]}).status_code == 200


def test_wrong_issuer_is_rejected(sso: dict) -> None:
    assert _finish(sso, {"iss": "https://evil.example.org/"}).status_code == 401


def test_non_string_subject_is_rejected(sso: dict) -> None:
    assert _finish(sso, {"sub": 12345}).status_code == 401
    assert _finish(sso, {"sub": ""}).status_code == 401


def test_finish_maps_idp_downtime_to_401(sso: dict) -> None:
    sso["captured"]["post_fails"] = True
    assert _finish(sso).status_code == 401


def test_single_audience_token_needs_no_azp(sso: dict) -> None:
    assert _finish(sso, {"aud": CLIENT}).status_code == 200


def test_multi_audience_token_requires_matching_azp(sso: dict) -> None:
    ok = _finish(sso, {"aud": [CLIENT, "other"], "azp": CLIENT})
    assert ok.status_code == 200
    assert _finish(sso, {"aud": [CLIENT, "other"]}).status_code == 401
    assert _finish(sso, {"aud": [CLIENT, "other"], "azp": "evil"}).status_code == 401


def test_three_audiences_are_fine_with_matching_azp(sso: dict) -> None:
    assert _finish(sso, {"aud": [CLIENT, "a", "b"], "azp": CLIENT}).status_code == 200


def test_wrong_azp_on_single_audience_is_rejected(sso: dict) -> None:
    assert _finish(sso, {"azp": "evil"}).status_code == 401


def _link_finish(
    sso: dict, headers: dict[str, str], **claims_extra: str | int | bool | None
) -> httpx.Response:
    start = sso["client"].post(ROOT + "link/start", headers=headers)
    assert start.status_code == 200, start.text
    body = start.json()
    query = parse_qs(urlsplit(body["url"]).query)
    claims = {
        "iss": ISS,
        "aud": CLIENT,
        "sub": "person",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "nonce": query["nonce"][0],
    }
    claims.update(claims_extra)
    sso["captured"]["id_token"] = jwt.encode(claims, sso["key"], algorithm="RS256")
    return sso["client"].post(
        ROOT + "link/finish",
        json={"transaction": body["transaction"], "state": query["state"][0], "code": "abc"},
        headers=headers,
    )


def test_linking_an_identity_owned_by_another_user_conflicts(sso: dict) -> None:
    first = login_as(sso["client"], "first@example.org")
    second = login_as(sso["client"], "second@example.org")
    assert _link_finish(sso, first).status_code == 200
    assert _link_finish(sso, second).status_code == 409


def test_new_identity_requires_a_verified_email(sso: dict) -> None:
    response = _finish(sso, {"email_verified": False})
    assert response.status_code == 409
    assert _finish(sso, {"email": 12345}).status_code == 409


def _forged_flow(start: dict, **changes: str | int | bool | None) -> str:
    """Re-sign the app-issued flow transaction with the server's own secret."""
    payload = jwt.decode(start["transaction"], key="", options={"verify_signature": False})
    for removed in [k for k, v in changes.items() if v is None]:
        payload.pop(removed, None)
    payload.update({k: v for k, v in changes.items() if v is not None})
    return jwt.encode(payload, oidc.auth_secret(), algorithm="HS256")


def test_flow_without_exp_is_rejected(sso: dict) -> None:
    start = _start(sso)
    forged = _forged_flow(start, exp=None)
    claims: dict = {}
    iat = int(time.time())
    claims = {
        "iss": ISS,
        "aud": CLIENT,
        "sub": "person",
        "iat": iat,
        "exp": iat + 300,
        "nonce": start["nonce"],
    }
    sso["captured"]["id_token"] = jwt.encode(claims, sso["key"], algorithm="RS256")
    response = sso["client"].post(
        ROOT + "finish",
        json={"transaction": forged, "state": start["state"], "code": "abc"},
    )
    assert response.status_code in (400, 401)


def test_flow_from_another_issuer_is_rejected(sso: dict) -> None:
    start = _start(sso)
    forged = _forged_flow(start, iss="https://evil.example.org/")
    claims = {
        "iss": ISS,
        "aud": CLIENT,
        "sub": "person",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "nonce": start["nonce"],
    }
    sso["captured"]["id_token"] = jwt.encode(claims, sso["key"], algorithm="RS256")
    response = sso["client"].post(
        ROOT + "finish",
        json={"transaction": forged, "state": start["state"], "code": "abc"},
    )
    assert response.status_code in (400, 401)


def test_id_token_without_iat_is_rejected(sso: dict) -> None:
    start = _start(sso)
    claims = {
        "iss": ISS,
        "aud": CLIENT,
        "sub": "person",
        "exp": int(time.time()) + 300,
        "nonce": start["nonce"],
    }
    sso["captured"]["id_token"] = jwt.encode(claims, sso["key"], algorithm="RS256")
    response = sso["client"].post(
        ROOT + "finish",
        json={"transaction": start["transaction"], "state": start["state"], "code": "abc"},
    )
    assert response.status_code == 401
