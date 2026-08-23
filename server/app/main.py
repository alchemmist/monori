"""Monori API. Money in/out of this API is integer kopecks everywhere."""

import contextlib
import os
import pathlib
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response

from monori.server.app.admin import record_api_usage
from monori.server.app.auth import AuthenticatedUser, current_user
from monori.server.app.deps import LIGHT_SNAPSHOT_TX_LIMIT, SnapshotResponse, conn, snapshot
from monori.server.app.routers import (
    accounts,
    admin,
    admin_sql,
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


app.include_router(auth_router.router)


app.include_router(admin.router)
app.include_router(admin_sql.router)


@app.middleware("http")
async def count_feature_usage(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Handle count feature usage."""
    response = await call_next(request)

    with contextlib.suppress(Exception):
        await run_in_threadpool(
            record_api_usage,
            request.url.path,
            request.headers.get("authorization"),
        )
    return response


STATIC_DIR = pathlib.Path(os.environ.get("MONORI_STATIC_DIR", "server/static"))


def _serve_spa(base: pathlib.Path, path: str) -> FileResponse:
    """
    Serve a file from ``base`` if the request maps to one inside it, else the.

    SPA index. The untrusted path is resolved (``..`` and symlinks collapsed).
    and must stay strictly under ``base`` before the file is opened, so absolute
    paths or traversal escaping ``base`` are rejected.
    """
    root = base.resolve()
    relative = pathlib.PurePosixPath(path)
    if path and not relative.is_absolute() and ".." not in relative.parts:
        target = root.joinpath(*relative.parts).resolve()
        if target.is_relative_to(root) and target.is_file():
            return FileResponse(str(target))
    return FileResponse(str(root / "index.html"))


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
def get_snapshot(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    *,
    light: bool = False,
    limit: Annotated[int, Query(ge=1, le=5000)] = LIGHT_SNAPSHOT_TX_LIMIT,
) -> SnapshotResponse:
    """
    Everything the app needs to render. ``light=1`` caps the transactions at the.

    newest ``limit`` rows so first paint doesn't wait on years of history; the.
    client fills the rest in the background over ``GET /api/transactions``.
    ``transactionsTotal`` always reports the full count. ``limit`` is bounds-
    checked whenever it is present, but only takes effect together with ``light``.
    """
    c = conn()
    try:
        return snapshot(c, user.id, tx_limit=limit if light else None)
    finally:
        c.close()


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
def api_not_found(path: str) -> None:
    """Handle api not found."""
    del path
    raise HTTPException(status_code=404, detail="Not Found")


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        """Handle spa."""
        return _serve_spa(STATIC_DIR, path)
