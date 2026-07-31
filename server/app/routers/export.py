from typing import Annotated, cast

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..auth import current_user
from ..deps import conn, snapshot
from ..workbook.export import WorkbookSnap, workbook_bytes

router = APIRouter(prefix="/api/export", tags=["export"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/xlsx")
def export_xlsx(user: Annotated[dict[str, object], Depends(current_user)]) -> Response:
    c = conn()
    try:
        snap = snapshot(c, cast("int", user["id"]))
    finally:
        c.close()
    return Response(
        content=workbook_bytes(cast("WorkbookSnap", snap)),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="monori-export.xlsx"'},
    )
