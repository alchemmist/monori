from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.auth import AuthenticatedUser, current_user
from app.deps import conn, snapshot
from app.workbook.export import workbook_bytes

router = APIRouter(prefix="/api/export", tags=["export"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/xlsx")
def export_xlsx(user: Annotated[AuthenticatedUser, Depends(current_user)]) -> Response:
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
