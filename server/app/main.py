"""Monori API. Money in/out of this API is integer kopecks everywhere."""

import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db as dbmod
from .importer import build_rules, categorize, parse_statement

app = FastAPI(title="monori")

STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent / "static"


def conn():
    return dbmod.connect()


def snapshot(c):
    cur = c.cursor()
    return {
        "groups": [
            dict(r)
            for r in cur.execute("SELECT id, name, sort, kind FROM category_groups ORDER BY sort")
        ],
        "categories": [
            {
                "id": r["id"],
                "groupId": r["group_id"],
                "name": r["name"],
                "keywords": r["keywords"],
                "sort": r["sort"],
                "archived": bool(r["archived"]),
            }
            for r in cur.execute("SELECT * FROM categories ORDER BY sort")
        ],
        "transactions": [
            {
                "id": r["id"],
                "date": r["date"],
                "amount": r["amount"],
                "description": r["description"],
                "bankCategory": r["bank_category"],
                "mcc": r["mcc"],
                "categoryId": r["category_id"],
                "comment": r["comment"],
                "source": r["source"],
            }
            for r in cur.execute("SELECT * FROM transactions ORDER BY date")
        ],
        "budgets": [
            {
                "categoryId": r["category_id"],
                "year": r["year"],
                "month": r["month"],
                "amount": r["amount"],
            }
            for r in cur.execute("SELECT * FROM budgets")
        ],
    }


@app.get("/api/snapshot")
def get_snapshot():
    c = conn()
    try:
        return snapshot(c)
    finally:
        c.close()


class BudgetCell(BaseModel):
    categoryId: int
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    amount: int


@app.put("/api/budgets")
def put_budget(cell: BudgetCell):
    c = conn()
    try:
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
        c.commit()
        return {"ok": True}
    finally:
        c.close()


class TxPatch(BaseModel):
    categoryId: int | None = None
    comment: str | None = None


@app.patch("/api/transactions/{tx_id}")
def patch_tx(tx_id: int, patch: TxPatch):
    c = conn()
    try:
        row = c.execute("SELECT id FROM transactions WHERE id=?", (tx_id,)).fetchone()
        if not row:
            raise HTTPException(404, "transaction not found")
        if patch.categoryId is not None:
            target = None if patch.categoryId == 0 else patch.categoryId
            if (
                target is not None
                and not c.execute("SELECT id FROM categories WHERE id=?", (target,)).fetchone()
            ):
                raise HTTPException(400, "unknown category")
            c.execute("UPDATE transactions SET category_id=? WHERE id=?", (target, tx_id))
        if patch.comment is not None:
            c.execute("UPDATE transactions SET comment=? WHERE id=?", (patch.comment, tx_id))
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@app.delete("/api/transactions/{tx_id}")
def delete_tx(tx_id: int):
    c = conn()
    try:
        cur = c.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
        c.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "transaction not found")
        return {"ok": True}
    finally:
        c.close()


class CategoryBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    groupId: int
    keywords: str = ""


@app.post("/api/categories")
def create_category(body: CategoryBody):
    c = conn()
    try:
        if not c.execute("SELECT id FROM category_groups WHERE id=?", (body.groupId,)).fetchone():
            raise HTTPException(400, "unknown group")
        if c.execute("SELECT id FROM categories WHERE name=?", (body.name,)).fetchone():
            raise HTTPException(409, "category with this name already exists")
        max_sort = c.execute("SELECT COALESCE(MAX(sort),0) FROM categories").fetchone()[0]
        cur = c.execute(
            "INSERT INTO categories (group_id, name, keywords, sort) VALUES (?, ?, ?, ?)",
            (body.groupId, body.name, body.keywords, max_sort + 1),
        )
        c.commit()
        return {"id": cur.lastrowid}
    finally:
        c.close()


class CategoryPatch(BaseModel):
    name: str | None = None
    groupId: int | None = None
    keywords: str | None = None


@app.patch("/api/categories/{cat_id}")
def patch_category(cat_id: int, patch: CategoryPatch):
    c = conn()
    try:
        if not c.execute("SELECT id FROM categories WHERE id=?", (cat_id,)).fetchone():
            raise HTTPException(404, "category not found")
        if patch.name is not None:
            dup = c.execute(
                "SELECT id FROM categories WHERE name=? AND id<>?", (patch.name, cat_id)
            ).fetchone()
            if dup:
                raise HTTPException(409, "category with this name already exists")
            c.execute("UPDATE categories SET name=? WHERE id=?", (patch.name, cat_id))
        if patch.groupId is not None:
            if not c.execute(
                "SELECT id FROM category_groups WHERE id=?", (patch.groupId,)
            ).fetchone():
                raise HTTPException(400, "unknown group")
            c.execute("UPDATE categories SET group_id=? WHERE id=?", (patch.groupId, cat_id))
        if patch.keywords is not None:
            c.execute("UPDATE categories SET keywords=? WHERE id=?", (patch.keywords, cat_id))
        c.commit()
        return {"ok": True}
    finally:
        c.close()


@app.delete("/api/categories/{cat_id}")
def delete_category(cat_id: int, reassignTo: int | None = None):
    """Deleting a category never shifts anything: transactions are reassigned
    (or left uncategorized), its budgets are removed by FK cascade."""
    c = conn()
    try:
        c.execute("PRAGMA foreign_keys=ON")
        if not c.execute("SELECT id FROM categories WHERE id=?", (cat_id,)).fetchone():
            raise HTTPException(404, "category not found")
        if reassignTo is not None:
            if not c.execute("SELECT id FROM categories WHERE id=?", (reassignTo,)).fetchone():
                raise HTTPException(400, "unknown reassign target")
            c.execute(
                "UPDATE transactions SET category_id=? WHERE category_id=?", (reassignTo, cat_id)
            )
        c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
        c.commit()
        return {"ok": True}
    finally:
        c.close()


class ImportBody(BaseModel):
    text: str


@app.post("/api/import/preview")
def import_preview(body: ImportBody):
    c = conn()
    try:
        rows, errors = parse_statement(body.text)
        groups = {r["id"]: r["kind"] for r in c.execute("SELECT id, kind FROM category_groups")}
        cats = [
            dict(r)
            for r in c.execute("SELECT id, name, keywords, group_id FROM categories ORDER BY sort")
        ]
        rules = build_rules(cats, groups)
        existing = {}
        for r in c.execute("SELECT hash, COUNT(*) n FROM transactions GROUP BY hash"):
            existing[r["hash"]] = r["n"]
        seen_in_batch: dict = {}
        for row in rows:
            row["categoryId"] = categorize(row["description"], row["amount"], rules)
            n_batch = seen_in_batch.get(row["hash"], 0)
            row["duplicate"] = existing.get(row["hash"], 0) > n_batch
            seen_in_batch[row["hash"]] = n_batch + 1
        return {"rows": rows, "errors": errors}
    finally:
        c.close()


class CommitRow(BaseModel):
    date: str
    amount: int
    description: str = ""
    bank_category: str = ""
    mcc: str = ""
    hash: str
    categoryId: int | None = None


class CommitBody(BaseModel):
    rows: list[CommitRow]


@app.post("/api/import/commit")
def import_commit(body: CommitBody):
    c = conn()
    try:
        for r in body.rows:
            c.execute(
                """INSERT INTO transactions
                   (date, amount, description, bank_category, mcc, category_id, hash, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'import')""",
                (r.date, r.amount, r.description, r.bank_category, r.mcc, r.categoryId, r.hash),
            )
        c.commit()
        return {"inserted": len(body.rows)}
    finally:
        c.close()


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        target = STATIC_DIR / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(STATIC_DIR / "index.html")
