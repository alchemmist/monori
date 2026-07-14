"""Monori API. Money in/out of this API is integer kopecks everywhere."""

import pathlib

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_token
from .deps import conn, snapshot
from .routers import budgets, categories, groups, imports, transactions

app = FastAPI(title="monori", docs_url="/api-docs", redoc_url="/api-redoc")

STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent / "static"
DOCS_DIR = pathlib.Path(__file__).resolve().parent.parent / "docs-static"


def _serve_spa(base: pathlib.Path, path: str):
    """Serve a file from ``base`` if the request maps to one inside it, else the
    SPA index. The containment check blocks path traversal (absolute paths or
    ``..`` escaping ``base``)."""
    root = base.resolve()
    if path:
        target = (root / path.lstrip("/")).resolve()
        if target.is_file() and target.is_relative_to(root):
            return FileResponse(target)
    return FileResponse(root / "index.html")


for _router in (
    groups.router,
    categories.router,
    transactions.router,
    budgets.router,
    imports.router,
):
    app.include_router(_router, dependencies=[Depends(require_token)])


@app.get("/api/snapshot", dependencies=[Depends(require_token)])
def get_snapshot():
    c = conn()
    try:
        return snapshot(c)
    finally:
        c.close()


if DOCS_DIR.is_dir():
    app.mount("/docs/assets", StaticFiles(directory=DOCS_DIR / "assets"), name="docs-assets")

    @app.get("/docs")
    @app.get("/docs/{path:path}")
    def docs_site(path: str = ""):
        return _serve_spa(DOCS_DIR, path)


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        return _serve_spa(STATIC_DIR, path)
