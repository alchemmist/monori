"""
The SPA catch-all must not swallow unknown /api paths — those still 404 as
JSON so typoed/removed endpoints don't silently return the app's index.html.
"""


def test_unknown_api_path_returns_json_404(anon):
    r = anon.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_unknown_api_path_404_for_write_methods(anon):
    assert anon.post("/api/nope", json={}).status_code == 404
    assert anon.delete("/api/nope").status_code == 404


def test_real_api_route_is_not_shadowed_by_the_guard(anon):
    # a registered but auth-protected endpoint still resolves to it (401), not 404
    assert anon.get("/api/snapshot").status_code == 401
