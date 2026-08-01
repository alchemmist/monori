import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ConfigDict, Field, JsonValue, model_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass

from ..auth import AuthenticatedUser, current_user
from ..db_records import CategoryOwnershipRecord, GoalGroupRecord
from ..deps import IdResponse, conn

router = APIRouter(prefix="/api/categories", tags=["categories"])


_CONFIG = ConfigDict(extra="forbid")


@pydantic_dataclass(config=_CONFIG)
class CategoryBody:
    name: str
    groupId: int
    keywords: str = ""
    goalTarget: int | None = None
    goalTargetDate: str | None = None


@pydantic_dataclass(config=_CONFIG)
class CategoryPatch:
    name: str | None = None
    groupId: int | None = None
    keywords: str | None = None
    archived: bool | None = None
    goalTarget: int | None = None
    goalTargetDate: str | None = None
    goalStatus: str | None = None
    goalTargetProvided: bool = Field(default=False, exclude=True, repr=False)
    goalTargetDateProvided: bool = Field(default=False, exclude=True, repr=False)

    @model_validator(mode="before")
    @classmethod
    def record_presence(cls, values: dict[str, JsonValue]) -> dict[str, JsonValue]:
        values["goalTargetProvided"] = "goalTarget" in values
        values["goalTargetDateProvided"] = "goalTargetDate" in values
        return values


@pydantic_dataclass(config=_CONFIG)
class ArchiveGoalBody:
    pass


@pydantic_dataclass(config=_CONFIG)
class Reorder:
    ids: list[int]


@pydantic_dataclass(config=_CONFIG)
class MergeBody:
    into: int


@pydantic_dataclass(config=_CONFIG)
class OkResponse:
    ok: bool


def _merge_keywords(a: str, b: str) -> str:
    seen, out = set(), []
    for kw in [*str(a or "").split("|"), *str(b or "").split("|")]:
        kw = kw.strip()
        key = kw.lower()
        if kw and key not in seen:
            seen.add(key)
            out.append(kw)
    return "|".join(out)


def _owned_category(c: sqlite3.Connection, cat_id: int, uid: int) -> CategoryOwnershipRecord | None:
    row = c.execute(
        "SELECT c.id, c.keywords, c.goal_target, t.type, t.is_goal"
        " FROM categories c JOIN category_groups g ON g.id = c.group_id"
        " JOIN category_group_types t ON t.id = g.type_id"
        " WHERE c.id=? AND g.user_id=?",
        (cat_id, uid),
    ).fetchone()
    return CategoryOwnershipRecord.from_row(row) if row is not None else None


def _name_taken(c: sqlite3.Connection, uid: int, name: str, except_id: int | None = None) -> bool:
    dup = c.execute(
        "SELECT c.id FROM categories c JOIN category_groups g ON g.id = c.group_id"
        " WHERE g.user_id=? AND c.name=? AND c.id<>?",
        (uid, name, except_id or 0),
    ).fetchone()
    return dup is not None


@router.post("")
def create_category(
    body: CategoryBody, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> IdResponse:
    uid = user.id
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name cannot be empty")
    c = conn()
    try:
        group = c.execute(
            "SELECT g.id, t.is_goal FROM category_groups g"
            " JOIN category_group_types t ON t.id=g.type_id"
            " WHERE g.id=? AND g.user_id=?",
            (body.groupId, uid),
        ).fetchone()
        if not group:
            raise HTTPException(400, "unknown group")
        group_record = GoalGroupRecord.from_row(group)
        keywords = body.keywords
        goal_target = body.goalTarget
        if group_record.is_goal and goal_target is None:
            raise HTTPException(400, "goalTarget is required for goal categories")
        if _name_taken(c, uid, name):
            raise HTTPException(409, "category with this name already exists")
        max_sort = c.execute(
            "SELECT COALESCE(MAX(c.sort),0) FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?",
            (uid,),
        ).fetchone()[0]
        cur = c.execute(
            "INSERT INTO categories (group_id, name, keywords, sort, goal_target, goal_status,"
            " goal_target_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                body.groupId,
                name,
                keywords,
                max_sort + 1,
                goal_target if group_record.is_goal else None,
                "active" if group_record.is_goal else None,
                body.goalTargetDate if group_record.is_goal else None,
            ),
        )
        c.commit()
        return IdResponse(id=cur.lastrowid)
    finally:
        c.close()


@router.patch("/{cat_id}")
def patch_category(
    cat_id: int, patch: CategoryPatch, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> OkResponse:
    uid = user.id
    c = conn()
    try:
        category = _owned_category(c, cat_id, uid)
        if not category:
            raise HTTPException(404, "category not found")
        if patch.name is not None:
            if _name_taken(c, uid, patch.name, except_id=cat_id):
                raise HTTPException(409, "category with this name already exists")
            c.execute("UPDATE categories SET name=? WHERE id=?", (patch.name, cat_id))
        goal_fields_allowed = category.is_goal
        if patch.groupId is not None:
            target_group = c.execute(
                "SELECT g.id, t.is_goal FROM category_groups g"
                " JOIN category_group_types t ON t.id=g.type_id"
                " WHERE g.id=? AND g.user_id=?",
                (patch.groupId, uid),
            ).fetchone()
            if not target_group:
                raise HTTPException(400, "unknown group")
            target_group_record = GoalGroupRecord.from_row(target_group)
            if (
                target_group_record.is_goal
                and not patch.goalTargetProvided
                and category.goal_target is None
            ):
                raise HTTPException(400, "goalTarget is required for goal categories")
            goal_fields_allowed = target_group_record.is_goal
            c.execute("UPDATE categories SET group_id=? WHERE id=?", (patch.groupId, cat_id))
            if not target_group_record.is_goal:
                goal_fields_allowed = False
                c.execute(
                    "UPDATE categories SET goal_target=NULL, goal_status=NULL,"
                    " goal_target_date=NULL WHERE id=?",
                    (cat_id,),
                )
        if patch.keywords is not None:
            c.execute("UPDATE categories SET keywords=? WHERE id=?", (patch.keywords, cat_id))
        if patch.archived is not None:
            c.execute(
                "UPDATE categories SET archived=? WHERE id=?",
                (1 if patch.archived else 0, cat_id),
            )
        if goal_fields_allowed and patch.goalTarget is not None:
            c.execute("UPDATE categories SET goal_target=? WHERE id=?", (patch.goalTarget, cat_id))
        if goal_fields_allowed and patch.goalTargetDateProvided:
            c.execute(
                "UPDATE categories SET goal_target_date=? WHERE id=?",
                (patch.goalTargetDate or None, cat_id),
            )
        if goal_fields_allowed and patch.goalStatus is not None:
            if patch.goalStatus not in ("active", "achieved"):
                raise HTTPException(400, "goalStatus must be 'active' or 'achieved'")
            c.execute("UPDATE categories SET goal_status=? WHERE id=?", (patch.goalStatus, cat_id))
        c.commit()
        return OkResponse(ok=True)
    finally:
        c.close()


@router.post("/{cat_id}/archive-goal")
def archive_goal(
    cat_id: int, body: ArchiveGoalBody, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> OkResponse:
    """Close a goal without rewriting its allocations or purchase history."""
    uid = user.id
    c = conn()
    try:
        row = _owned_category(c, cat_id, uid)
        if not row or not row.is_goal:
            raise HTTPException(404, "goal not found")
        c.execute("UPDATE categories SET archived=1, goal_status='archived' WHERE id=?", (cat_id,))
        c.commit()
        return OkResponse(ok=True)
    finally:
        c.close()


@router.delete("/{cat_id}")
def delete_category(
    cat_id: int, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> OkResponse:
    """
    Deleting a category never shifts anything: its transactions are left
    uncategorized and its budgets are removed by FK cascade.

    Moving the transactions somewhere instead is what /merge is for. Delete used
    to take a reassignTo, which was the same move without the same-kind check
    merge enforces — so the income/expense invariant was one API call from being
    bypassed. There is now exactly one path that moves transactions.
    """
    uid = user.id
    c = conn()
    try:
        c.execute("PRAGMA foreign_keys=ON")
        if not _owned_category(c, cat_id, uid):
            raise HTTPException(404, "category not found")
        if c.execute("SELECT 1 FROM splits WHERE category_id=? LIMIT 1", (cat_id,)).fetchone():
            raise HTTPException(409, "category is used by transaction splits; merge it first")
        c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
        c.commit()
        return OkResponse(ok=True)
    finally:
        c.close()


@router.post("/reorder")
def reorder_categories(
    body: Reorder, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> OkResponse:
    uid = user.id
    c = conn()
    try:
        known = {
            r["id"]
            for r in c.execute(
                "SELECT c.id FROM categories c JOIN category_groups g ON g.id = c.group_id"
                " WHERE g.user_id=?",
                (uid,),
            )
        }
        if set(body.ids) != known:
            raise HTTPException(400, "ids must list every existing category exactly once")
        for sort, cid in enumerate(body.ids, 1):
            c.execute("UPDATE categories SET sort=? WHERE id=?", (sort, cid))
        c.commit()
        return OkResponse(ok=True)
    finally:
        c.close()


@router.post("/{cat_id}/merge")
def merge_category(
    cat_id: int, body: MergeBody, user: Annotated[AuthenticatedUser, Depends(current_user)]
) -> OkResponse:
    """
    Combine a category into another: its transactions move to the target,
    keywords are unioned, budgets are summed month by month, then the source
    category is deleted. Summing matters: the spending moves across, so a
    dropped plan would read as a retroactive overspend on the target.

    Income and expense never mix: budgeting and analytics read the sign off the
    group kind, so a cross-kind merge would silently reinterpret the whole
    moved history.
    """
    uid = user.id
    c = conn()
    try:
        c.execute("PRAGMA foreign_keys=ON")
        src = _owned_category(c, cat_id, uid)
        if not src:
            raise HTTPException(404, "category not found")
        if body.into == cat_id:
            raise HTTPException(400, "cannot merge a category into itself")
        dst = _owned_category(c, body.into, uid)
        if not dst:
            raise HTTPException(400, "unknown merge target")
        if src.type != dst.type:
            raise HTTPException(400, "cannot merge across income and expense")
        c.execute("UPDATE transactions SET category_id=? WHERE category_id=?", (body.into, cat_id))
        c.execute("UPDATE splits SET category_id=? WHERE category_id=?", (body.into, cat_id))
        c.execute(
            "UPDATE categories SET keywords=? WHERE id=?",
            (_merge_keywords(dst.keywords, src.keywords), body.into),
        )
        c.execute(
            "INSERT INTO budgets (category_id, year, month, amount)"
            " SELECT ?, year, month, amount FROM budgets WHERE category_id=?"
            " ON CONFLICT (category_id, year, month)"
            " DO UPDATE SET amount = amount + excluded.amount",
            (body.into, cat_id),
        )
        c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
        c.commit()
        return OkResponse(ok=True)
    finally:
        c.close()
