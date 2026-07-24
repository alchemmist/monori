"""
Monori API. Money in/out of this API is integer kopecks everywhere.
"""

import contextlib
import os
import pathlib
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .admin import record_api_usage
from .auth import current_user
from .deps import conn, snapshot
from .routers import (
    accounts,
    admin,
    auth_router,
    budgets,
    categories,
    connections,
    export,
    groups,
    imports,
    transactions,
    transfers,
)

app = FastAPI(title="monori", docs_url="/api-docs", redoc_url="/api-redoc")

# authentication endpoints are public (they mint the tokens the rest would need)
app.include_router(auth_router.router)

# admin routes carry their own guard (admin_user wraps current_user with a 403)
app.include_router(admin.router)


@app.middleware("http")
async def count_feature_usage(request, call_next):
    response = await call_next(request)
    # analytics must never break the request it observes
    with contextlib.suppress(Exception):
        record_api_usage(request.url.path, request.headers.get("authorization"))
    return response


STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent / "static"


def _serve_spa(base: pathlib.Path, path: str):
    """
    Serve a file from ``base`` if the request maps to one inside it, else the
    SPA index. The untrusted path is resolved (``..`` and symlinks collapsed)
    and must stay strictly under ``base`` before the file is opened, so absolute
    paths or traversal escaping ``base`` are rejected.
    """
    root = os.path.realpath(base)
    if path:
        target = os.path.realpath(os.path.join(root, path.lstrip("/")))
        if target.startswith(root + os.sep) and os.path.isfile(target):
            return FileResponse(target)
    return FileResponse(os.path.join(root, "index.html"))


for _router in (
    accounts.router,
    groups.router,
    categories.router,
    transactions.router,
    transfers.router,
    budgets.router,
    imports.router,
    connections.router,
    export.router,
):
    app.include_router(_router, dependencies=[Depends(current_user)])


@app.get("/api/snapshot")
def get_snapshot(user: Annotated[dict, Depends(current_user)]):
    c = conn()
    try:
        return snapshot(c, user["id"])
    finally:
        c.close()


# unknown /api/* paths must 404 as JSON, not fall through to the SPA index below
# (declared after the real API routers so only unregistered paths reach it)
@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
def api_not_found(path: str):
    raise HTTPException(status_code=404, detail="Not Found")


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    # one SPA serves everything: the app, the marketing landing (/welcome) and
    # the docs (/docs/*) — its client router renders by full path
    @app.get("/{path:path}")
    def spa(path: str):
        return _serve_spa(STATIC_DIR, path)
