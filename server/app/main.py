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
        target = DOCS_DIR / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(DOCS_DIR / "index.html")


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        target = STATIC_DIR / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(STATIC_DIR / "index.html")
