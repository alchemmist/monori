from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import current_user
from ..deps import conn

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


class BudgetCell(BaseModel):
    categoryId: int
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    amount: int


class BulkBody(BaseModel):
    cells: list[BudgetCell]


class CopyBody(BaseModel):
    fromYear: int = Field(ge=2000, le=2100)
    toYear: int = Field(ge=2000, le=2100)
    fromMonth: int | None = Field(default=None, ge=1, le=12)
    toMonth: int | None = Field(default=None, ge=1, le=12)


def _set_cell(c, cell: BudgetCell, uid):
    if not c.execute(
        "SELECT c.id FROM categories c JOIN category_groups g ON g.id = c.group_id"
        " WHERE c.id=? AND g.user_id=?",
        (cell.categoryId, uid),
    ).fetchone():
        raise HTTPException(400, "unknown category")
    if cell.amount == 0:
        c.execute(
            "DELETE FROM budgets WHERE category_id=? AND year=? AND month=?",
            (cell.categoryId, cell.year, cell.month),
        )
    else:
        c.execute(
            """INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)
               ON CONFLICT(category_id, year, month) DO UPDATE SET amount=excluded.amount""",
            (cell.categoryId, cell.year, cell.month, cell.amount),
        )


@router.put("")
def put_budget(cell: BudgetCell, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        _set_cell(c, cell, uid)
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.post("/bulk")
def bulk_budgets(body: BulkBody, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        for cell in body.cells:
            _set_cell(c, cell, uid)
        c.commit()
        return {"set": len(body.cells)}
    finally:
        c.close()


@router.post("/copy")
def copy_budgets(body: CopyBody, user: Annotated[dict, Depends(current_user)]):
    """Copy month->month (both months given) or a whole year->year (months
    omitted). The destination scope is cleared first, so it becomes an exact
    copy of the source."""
    uid = user["id"]
    month_mode = body.fromMonth is not None and body.toMonth is not None
    year_mode = body.fromMonth is None and body.toMonth is None
    if not (month_mode or year_mode):
        raise HTTPException(400, "give both fromMonth and toMonth, or neither")
    c = conn()
    try:
        if month_mode:
            src = c.execute(
                "SELECT category_id, amount FROM budgets WHERE year=? AND month=?"
                " AND category_id IN (SELECT c.id FROM categories c"
                " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?)",
                (body.fromYear, body.fromMonth, uid),
            ).fetchall()
            c.execute(
                "DELETE FROM budgets WHERE year=? AND month=?"
                " AND category_id IN (SELECT c.id FROM categories c"
                " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?)",
                (body.toYear, body.toMonth, uid),
            )
            for r in src:
                c.execute(
                    "INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)",
                    (r["category_id"], body.toYear, body.toMonth, r["amount"]),
                )
        else:
            src = c.execute(
                "SELECT category_id, month, amount FROM budgets WHERE year=?"
                " AND category_id IN (SELECT c.id FROM categories c"
                " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?)",
                (body.fromYear, uid),
            ).fetchall()
            c.execute(
                "DELETE FROM budgets WHERE year=? AND category_id IN (SELECT c.id FROM categories c"
                " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?)",
                (body.toYear, uid),
            )
            for r in src:
                c.execute(
                    "INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)",
                    (r["category_id"], body.toYear, r["month"], r["amount"]),
                )
        c.commit()
        return {"copied": len(src)}
    finally:
        c.close()
