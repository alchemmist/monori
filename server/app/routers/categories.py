from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import current_user
from ..deps import conn

router = APIRouter(prefix="/api/categories", tags=["categories"])

_OWNED = (
    "SELECT c.id, c.keywords FROM categories c"
    " JOIN category_groups g ON g.id = c.group_id WHERE c.id=? AND g.user_id=?"
)


class CategoryBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    groupId: int
    keywords: str = ""


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    groupId: int | None = None
    keywords: str | None = None
    archived: bool | None = None


class Reorder(BaseModel):
    ids: list[int]


class MergeBody(BaseModel):
    into: int


def _merge_keywords(a, b):
    seen, out = set(), []
    for kw in [*str(a or "").split("|"), *str(b or "").split("|")]:
        kw = kw.strip()
        key = kw.lower()
        if kw and key not in seen:
            seen.add(key)
            out.append(kw)
    return "|".join(out)


def _owned_category(c, cat_id, uid):
    return c.execute(_OWNED, (cat_id, uid)).fetchone()


def _name_taken(c, uid, name, except_id=None):
    dup = c.execute(
        "SELECT c.id FROM categories c JOIN category_groups g ON g.id = c.group_id"
        " WHERE g.user_id=? AND c.name=? AND c.id<>?",
        (uid, name, except_id or 0),
    ).fetchone()
    return dup is not None


@router.post("")
def create_category(body: CategoryBody, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        if not c.execute(
            "SELECT id FROM category_groups WHERE id=? AND user_id=?", (body.groupId, uid)
        ).fetchone():
            raise HTTPException(400, "unknown group")
        if _name_taken(c, uid, body.name):
            raise HTTPException(409, "category with this name already exists")
        max_sort = c.execute(
            "SELECT COALESCE(MAX(c.sort),0) FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=?",
            (uid,),
        ).fetchone()[0]
        cur = c.execute(
            "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, ?, ?, ?)",
            (body.groupId, body.name, body.keywords, max_sort + 1),
        )
        c.commit()
        return {"id": cur.lastrowid}
    finally:
        c.close()


@router.patch("/{cat_id}")
def patch_category(cat_id: int, patch: CategoryPatch, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        if not _owned_category(c, cat_id, uid):
            raise HTTPException(404, "category not found")
        if patch.name is not None:
            if _name_taken(c, uid, patch.name, except_id=cat_id):
                raise HTTPException(409, "category with this name already exists")
            c.execute("UPDATE categories SET name=? WHERE id=?", (patch.name, cat_id))
        if patch.groupId is not None:
            if not c.execute(
                "SELECT id FROM category_groups WHERE id=? AND user_id=?", (patch.groupId, uid)
            ).fetchone():
                raise HTTPException(400, "unknown group")
            c.execute("UPDATE categories SET group_id=? WHERE id=?", (patch.groupId, cat_id))
        if patch.keywords is not None:
            c.execute("UPDATE categories SET keywords=? WHERE id=?", (patch.keywords, cat_id))
        if patch.archived is not None:
            c.execute(
                "UPDATE categories SET archived=? WHERE id=?", (1 if patch.archived else 0, cat_id)
            )
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.delete("/{cat_id}")
def delete_category(
    cat_id: int,
    user: Annotated[dict, Depends(current_user)],
    reassignTo: int | None = None,
):
    """Deleting a category never shifts anything: transactions are reassigned
    (or left uncategorized), its budgets are removed by FK cascade."""
    uid = user["id"]
    c = conn()
    try:
        c.execute("PRAGMA foreign_keys=ON")
        if not _owned_category(c, cat_id, uid):
            raise HTTPException(404, "category not found")
        if reassignTo is not None:
            if not _owned_category(c, reassignTo, uid):
                raise HTTPException(400, "unknown reassign target")
            c.execute(
                "UPDATE transactions SET category_id=? WHERE category_id=?", (reassignTo, cat_id)
            )
        c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.post("/reorder")
def reorder_categories(body: Reorder, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
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
        return {"ok": True}
    finally:
        c.close()


@router.post("/{cat_id}/merge")
def merge_category(cat_id: int, body: MergeBody, user: Annotated[dict, Depends(current_user)]):
    """Combine a category into another: its transactions move to the target,
    keywords are unioned, then the source category is deleted."""
    uid = user["id"]
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
        c.execute("UPDATE transactions SET category_id=? WHERE category_id=?", (body.into, cat_id))
        c.execute(
            "UPDATE categories SET keywords=? WHERE id=?",
            (_merge_keywords(dst["keywords"], src["keywords"]), body.into),
        )
        c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
        c.commit()
        return {"ok": True}
    finally:
        c.close()
