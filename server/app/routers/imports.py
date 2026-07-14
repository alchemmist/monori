from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..deps import conn
from ..importer import build_rules, categorize, parse_statement, tx_hash

router = APIRouter(prefix="/api/import", tags=["import"])


class ImportBody(BaseModel):
    text: str


class CommitRow(BaseModel):
    date: str
    amount: int
    description: str = ""
    bank_category: str = ""
    mcc: str = ""
    categoryId: int | None = None


class CommitBody(BaseModel):
    accountId: int
    rows: list[CommitRow]


@router.post("/preview")
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


@router.post("/commit")
def import_commit(body: CommitBody):
    """Server-side dedup: the hash is recomputed here (never trusted from the
    client) and rows whose hash already exists — or repeats within the batch —
    are skipped, so a double-submit can't create duplicates."""
    c = conn()
    try:
        if not c.execute("SELECT id FROM accounts WHERE id=?", (body.accountId,)).fetchone():
            raise HTTPException(400, "unknown account")
        existing = {}
        for r in c.execute("SELECT hash, COUNT(*) n FROM transactions GROUP BY hash"):
            existing[r["hash"]] = r["n"]
        seen_in_batch: dict = {}
        inserted = skipped = 0
        for r in body.rows:
            h = tx_hash(r.date, r.amount, r.description)
            n_batch = seen_in_batch.get(h, 0)
            seen_in_batch[h] = n_batch + 1
            if n_batch < existing.get(h, 0):
                skipped += 1
                continue
            c.execute(
                """INSERT INTO transactions
                   (date, amount, description, bank_category, mcc, category_id, account_id,
                    hash, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'import')""",
                (
                    r.date,
                    r.amount,
                    r.description,
                    r.bank_category,
                    r.mcc,
                    r.categoryId,
                    body.accountId,
                    h,
                ),
            )
            inserted += 1
        c.commit()
        return {"inserted": inserted, "skipped": skipped}
    finally:
        c.close()
