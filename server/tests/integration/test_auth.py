import pytest

pytestmark = pytest.mark.integration


def test_api_token_guards_every_route(client, monkeypatch):
    monkeypatch.setenv("MONORI_API_TOKEN", "s3cret")
    hdr = {"Authorization": "Bearer s3cret"}

    denied = client.get("/api/snapshot")
    assert denied.status_code == 401 and "token" in denied.json()["detail"].lower()
    assert client.get("/api/groups").status_code == 401
    assert client.post("/api/groups", json={"name": "X", "kind": "expense"}).status_code == 401
    assert client.get("/api/snapshot", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/snapshot", headers={"Authorization": "s3cret"}).status_code == 401

    assert client.get("/api/snapshot", headers=hdr).status_code == 200
    assert (
        client.post("/api/groups", json={"name": "X", "kind": "expense"}, headers=hdr).status_code
        == 200
    )
