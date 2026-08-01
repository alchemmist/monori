from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from app.auth import AuthenticatedUser, current_user
from app.db_records import GroupRecord
from app.deps import GroupResponse, IdResponse, conn, serialize_group

router = APIRouter(prefix="/api/groups", tags=["groups"])


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class GroupBody:
    name: str
    kind: str


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class GroupPatch:
    name: str | None = None
    kind: str | None = None


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class Reorder:
    ids: list[int]


@router.get("")
def list_groups(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[GroupResponse]:
    uid = user.id
    c = conn()
    try:
        return [
            serialize_group(GroupRecord.from_row(r))
            for r in c.execute(
                "SELECT g.id, g.name, g.sort, t.type AS kind FROM category_groups g"
                " JOIN category_group_types t ON t.id=g.type_id"
                " WHERE g.user_id=? ORDER BY g.sort",
                (uid,),
            )
        ]
    finally:
        c.close()


@router.post("")
def create_group(
    body: GroupBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> IdResponse:
    uid = user.id
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name cannot be empty")
    c = conn()
    try:
        group_type = c.execute(
            "SELECT id FROM category_group_types WHERE type=?",
            (body.kind,),
        ).fetchone()
        if not group_type:
            raise HTTPException(400, "kind must be 'income', 'expense', or 'goal'")
        if c.execute(
            "SELECT id FROM category_groups WHERE user_id=? AND name=?",
            (uid, name),
        ).fetchone():
            raise HTTPException(409, "group with this name already exists")
        max_sort = c.execute(
            "SELECT COALESCE(MAX(sort),0) FROM category_groups WHERE user_id=?",
            (uid,),
        ).fetchone()[0]
        cur = c.execute(
            "INSERT INTO category_groups (user_id, name, sort, type_id) VALUES (?, ?, ?, ?)",
            (uid, name, max_sort + 1, group_type["id"]),
        )
        c.commit()
        return IdResponse(id=cur.lastrowid)
    finally:
        c.close()


@router.patch("/{group_id}")
def patch_group(
    group_id: int,
    patch: GroupPatch,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> dict[str, bool]:
    uid = user.id
    c = conn()
    try:
        if not c.execute(
            "SELECT id FROM category_groups WHERE id=? AND user_id=?",
            (group_id, uid),
        ).fetchone():
            raise HTTPException(404, "group not found")
        patch_name = patch.name
        if patch_name is not None:
            dup = c.execute(
                "SELECT id FROM category_groups WHERE user_id=? AND name=? AND id<>?",
                (uid, patch_name, group_id),
            ).fetchone()
            if dup:
                raise HTTPException(409, "group with this name already exists")
            c.execute("UPDATE category_groups SET name=? WHERE id=?", (patch_name, group_id))
        patch_kind = patch.kind
        if patch_kind is not None:
            group_type = c.execute(
                "SELECT id FROM category_group_types WHERE type=?",
                (patch_kind,),
            ).fetchone()
            if not group_type:
                raise HTTPException(400, "kind must be 'income', 'expense', or 'goal'")
            c.execute(
                "UPDATE category_groups SET type_id=? WHERE id=?",
                (group_type["id"], group_id),
            )
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.delete("/{group_id}")
def delete_group(
    group_id: int,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> dict[str, bool]:
    uid = user.id
    c = conn()
    try:
        if not c.execute(
            "SELECT id FROM category_groups WHERE id=? AND user_id=?",
            (group_id, uid),
        ).fetchone():
            raise HTTPException(404, "group not found")
        cur = c.execute(
            "DELETE FROM category_groups WHERE id=?"
            " AND NOT EXISTS (SELECT 1 FROM categories WHERE group_id=?)",
            (group_id, group_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "group still has categories; move or delete them first")
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@router.post("/reorder")
def reorder_groups(
    body: Reorder,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> dict[str, bool]:
    uid = user.id
    c = conn()
    try:
        known = {
            r["id"] for r in c.execute("SELECT id FROM category_groups WHERE user_id=?", (uid,))
        }
        if set(body.ids) != known:
            raise HTTPException(400, "ids must list every existing group exactly once")
        for sort, gid in enumerate(body.ids, 1):
            c.execute("UPDATE category_groups SET sort=? WHERE id=?", (sort, gid))
        c.commit()
        return {"ok": True}
    finally:
        c.close()
