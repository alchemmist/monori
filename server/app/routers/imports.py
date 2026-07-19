from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import current_user
from ..deps import conn
from ..importer import build_rules, categorize, parse_statement
from ..ingest import commit_rows, existing_hash_counts

router = APIRouter(prefix="/api/import", tags=["import"])


class ImportBody(BaseModel):
    text: str
    accountId: int | None = None


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


def _load_user_rules(c, uid):
    groups = {
        r["id"]: r["kind"]
        for r in c.execute("SELECT id, kind FROM category_groups WHERE user_id=?", (uid,))
    }
    cats = [
        dict(r)
        for r in c.execute(
            "SELECT c.id, c.name, c.keywords, c.group_id FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id WHERE g.user_id=? ORDER BY c.sort",
            (uid,),
        )
    ]
    return build_rules(cats, groups)


def _owned_account(c, account_id, uid):
    return (
        account_id is not None
        and c.execute(
            "SELECT id FROM accounts WHERE id=? AND user_id=?", (account_id, uid)
        ).fetchone()
        is not None
    )


@router.post("/preview")
def import_preview(body: ImportBody, user: Annotated[dict, Depends(current_user)]):
    uid = user["id"]
    c = conn()
    try:
        rows, errors = parse_statement(body.text)
        rules = _load_user_rules(c, uid)
        account_id = body.accountId if _owned_account(c, body.accountId, uid) else None
        existing = existing_hash_counts(c, account_id)
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
def import_commit(body: CommitBody, user: Annotated[dict, Depends(current_user)]):
    """Server-side dedup: rows whose hash already exists — or repeats within the
    batch — are skipped, so a double-submit can't create duplicates."""
    uid = user["id"]
    c = conn()
    try:
        if not _owned_account(c, body.accountId, uid):
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
