from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..deps import conn
from ..importer import categorize, parse_statement
from ..ingest import commit_rows, existing_hash_counts, load_rules

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
        rules = load_rules(c)
        existing = existing_hash_counts(c)
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
    """Server-side dedup: rows whose hash already exists — or repeats within the
    batch — are skipped, so a double-submit can't create duplicates."""
    c = conn()
    try:
        if not c.execute("SELECT id FROM accounts WHERE id=?", (body.accountId,)).fetchone():
            raise HTTPException(400, "unknown account")
        rows = [
            {
                "date": r.date,
                "amount": r.amount,
                "description": r.description,
                "bank_category": r.bank_category,
                "mcc": r.mcc,
                "category_id": r.categoryId,
            }
            for r in body.rows
        ]
        inserted, skipped = commit_rows(c, body.accountId, rows, source="import")
        c.commit()
        return {"inserted": inserted, "skipped": skipped}
    finally:
        c.close()
