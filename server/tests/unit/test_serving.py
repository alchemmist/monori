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


def test_serve_spa_serves_contained_file(tmp_path):
    from app.main import _serve_spa

    (tmp_path / "index.html").write_text("i")
    (tmp_path / "favicon.ico").write_text("f")
    assert _serve_spa(tmp_path, "favicon.ico").path == str(tmp_path / "favicon.ico")


def test_serve_spa_falls_back_to_index_for_unknown_route(tmp_path):
    from app.main import _serve_spa

    (tmp_path / "index.html").write_text("i")
    assert _serve_spa(tmp_path, "some/spa/route").path == str(tmp_path / "index.html")


def test_serve_spa_rejects_traversal(tmp_path):
    from app.main import _serve_spa

    (tmp_path / "index.html").write_text("i")
    (tmp_path.parent / "secret.txt").write_text("s")
    assert _serve_spa(tmp_path, "../secret.txt").path == str(tmp_path / "index.html")
