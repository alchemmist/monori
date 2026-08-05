"""Provide backend functionality."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from monori.server.app.auth import AuthenticatedUser, current_user
from monori.server.app.deps import conn, snapshot
from monori.server.app.workbook.export import workbook_bytes

router = APIRouter(prefix="/api/export", tags=["export"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/xlsx")
def export_xlsx(user: Annotated[AuthenticatedUser, Depends(current_user)]) -> Response:
    """Handle export xlsx."""
    c = conn()
    try:
        snap = snapshot(c, user.id)
    finally:
        c.close()
    return Response(
        content=workbook_bytes(snap),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="monori-export.xlsx"'},
    )
