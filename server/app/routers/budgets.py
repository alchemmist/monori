import sqlite3
from typing import Annotated, NotRequired, TypedDict

from fastapi import APIRouter, Depends, HTTPException

from ..auth import AuthenticatedUser, current_user
from ..deps import conn

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


class BudgetCell(TypedDict):
    categoryId: int
    year: int
    month: int
    amount: int


class BulkBody(TypedDict):
    cells: list[BudgetCell]


class CopyBody(TypedDict):
    fromYear: int
    toYear: int
    fromMonth: NotRequired[int | None]
    toMonth: NotRequired[int | None]


def _set_cell(c: sqlite3.Connection, cell: BudgetCell, uid: int) -> None:
    if not 1 <= cell["month"] <= 12:
        raise HTTPException(422, "month must be between 1 and 12")
    if not c.execute(
        "SELECT c.id FROM categories c JOIN category_groups g ON g.id = c.group_id"
        " WHERE c.id=? AND g.user_id=?",
        (cell["categoryId"], uid),
    ).fetchone():
        raise HTTPException(400, "unknown category")
    if cell["amount"] == 0:
        c.execute(
            "DELETE FROM budgets WHERE category_id=? AND year=? AND month=?",
            (cell["categoryId"], cell["year"], cell["month"]),
        )
    else:
        c.execute(
            """INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)
               ON CONFLICT(category_id, year, month) DO UPDATE SET amount=excluded.amount""",
            (cell["categoryId"], cell["year"], cell["month"], cell["amount"]),
        )


@router.put("")
def put_budget(
    cell: BudgetCell, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> dict[str, bool]:
    uid = user.id
    c = conn()
    try:
        _set_cell(c, cell, uid)
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.post("/bulk")
def bulk_budgets(
    body: BulkBody, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> dict[str, int]:
    uid = user.id
    c = conn()
    try:
        for cell in body["cells"]:
            _set_cell(c, cell, uid)
        c.commit()
        return {"set": len(body["cells"])}
    finally:
        c.close()


@router.post("/copy")
def copy_budgets(
    body: CopyBody, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> dict[str, int]:
    """
    Copy month->month (both months given) or a whole year->year (months
    omitted). The destination scope is cleared first, so it becomes an exact
    copy of the source.
    """
    uid = user.id
    from_month = body.get("fromMonth")
    to_month = body.get("toMonth")
    month_mode = from_month is not None and to_month is not None
    year_mode = from_month is None and to_month is None
    if not (month_mode or year_mode):
        raise HTTPException(400, "give both fromMonth and toMonth, or neither")
    c = conn()
    try:
        if month_mode:
            src = c.execute(
                "SELECT category_id, amount FROM budgets WHERE year=? AND month=?"
                " AND category_id IN (SELECT c.id FROM categories c"
                " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?)",
                (body["fromYear"], from_month, uid),
            ).fetchall()
            c.execute(
                "DELETE FROM budgets WHERE year=? AND month=?"
                " AND category_id IN (SELECT c.id FROM categories c"
                " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?)",
                (body["toYear"], to_month, uid),
            )
            for r in src:
                c.execute(
                    "INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)",
                    (r["category_id"], body["toYear"], to_month, r["amount"]),
                )
        else:
            src = c.execute(
                "SELECT category_id, month, amount FROM budgets WHERE year=?"
                " AND category_id IN (SELECT c.id FROM categories c"
                " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?)",
                (body["fromYear"], uid),
            ).fetchall()
            c.execute(
                "DELETE FROM budgets WHERE year=? AND category_id IN (SELECT c.id FROM categories c"
                " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?)",
                (body["toYear"], uid),
            )
            for r in src:
                c.execute(
                    "INSERT INTO budgets (category_id, year, month, amount) VALUES (?, ?, ?, ?)",
                    (r["category_id"], body["toYear"], r["month"], r["amount"]),
                )
        c.commit()
        return {"copied": len(src)}
    finally:
        c.close()
