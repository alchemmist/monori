from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..deps import conn, serialize_group

router = APIRouter(prefix="/api/groups", tags=["groups"])

KINDS = ("income", "expense")


class GroupBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str


class GroupPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: str | None = None


class Reorder(BaseModel):
    ids: list[int]


@router.get("")
def list_groups():
    c = conn()
    try:
        return [
            serialize_group(r)
            for r in c.execute("SELECT id, name, sort, kind FROM category_groups ORDER BY sort")
        ]
    finally:
        c.close()


@router.post("")
def create_group(body: GroupBody):
    c = conn()
    try:
        if body.kind not in KINDS:
            raise HTTPException(400, "kind must be 'income' or 'expense'")
        if c.execute("SELECT id FROM category_groups WHERE name=?", (body.name,)).fetchone():
            raise HTTPException(409, "group with this name already exists")
        max_sort = c.execute("SELECT COALESCE(MAX(sort),0) FROM category_groups").fetchone()[0]
        cur = c.execute(
            "INSERT INTO category_groups (name, sort, kind) VALUES (?, ?, ?)",
            (body.name, max_sort + 1, body.kind),
        )
        c.commit()
        return {"id": cur.lastrowid}
    finally:
        c.close()


@router.patch("/{group_id}")
def patch_group(group_id: int, patch: GroupPatch):
    c = conn()
    try:
        if not c.execute("SELECT id FROM category_groups WHERE id=?", (group_id,)).fetchone():
            raise HTTPException(404, "group not found")
        if patch.name is not None:
            dup = c.execute(
                "SELECT id FROM category_groups WHERE name=? AND id<>?", (patch.name, group_id)
            ).fetchone()
            if dup:
                raise HTTPException(409, "group with this name already exists")
            c.execute("UPDATE category_groups SET name=? WHERE id=?", (patch.name, group_id))
        if patch.kind is not None:
            if patch.kind not in KINDS:
                raise HTTPException(400, "kind must be 'income' or 'expense'")
            c.execute("UPDATE category_groups SET kind=? WHERE id=?", (patch.kind, group_id))
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.delete("/{group_id}")
def delete_group(group_id: int):
    c = conn()
    try:
        if not c.execute("SELECT id FROM category_groups WHERE id=?", (group_id,)).fetchone():
            raise HTTPException(404, "group not found")
        n = c.execute("SELECT COUNT(*) FROM categories WHERE group_id=?", (group_id,)).fetchone()[0]
        if n:
            raise HTTPException(409, "group still has categories; move or delete them first")
        c.execute("DELETE FROM category_groups WHERE id=?", (group_id,))
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.post("/reorder")
def reorder_groups(body: Reorder):
    c = conn()
    try:
        known = {r["id"] for r in c.execute("SELECT id FROM category_groups")}
        if set(body.ids) != known:
            raise HTTPException(400, "ids must list every existing group exactly once")
        for sort, gid in enumerate(body.ids, 1):
            c.execute("UPDATE category_groups SET sort=? WHERE id=?", (sort, gid))
        c.commit()
        return {"ok": True}
    finally:
        c.close()
