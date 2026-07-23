import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..auth import current_user
from ..deps import conn
from ..importer import build_rules, categorize, parse_statement
from ..ingest import commit_rows, existing_hash_counts
from ..workbook.apply import apply_workbook
from ..workbook.importer import WorkbookError, parse_workbook

router = APIRouter(prefix="/api/import", tags=["import"])

WORKBOOK_MAX_BYTES = 20 * 1024 * 1024


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


async def _read_workbook_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > WORKBOOK_MAX_BYTES:
        raise HTTPException(413, "workbook is too large")
    if not data:
        raise HTTPException(400, "empty upload")
    return data


def _workbook_preview_summary(parsed):
    tx = parsed["transactions"]
    by_year: dict[str, int] = {}
    for row in tx:
        year = row["date"][:4]
        by_year[year] = by_year.get(year, 0) + 1
    return {
        "groups": len(parsed["groups"]),
        "categories": len(parsed["categories"]),
        "transactions": len(tx),
        "transactionsByYear": dict(sorted(by_year.items())),
        "budgetCells": len(parsed["budgets"]),
        "accountMarkers": sorted({row["marker"] for row in tx}),
        "warnings": parsed["warnings"],
        "errors": parsed["errors"],
    }


@router.post("/workbook/preview")
async def workbook_preview(
    user: Annotated[dict, Depends(current_user)],
    file: Annotated[UploadFile, File()],
):
    data = await _read_workbook_upload(file)
    try:
        parsed = parse_workbook(data)
    except WorkbookError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _workbook_preview_summary(parsed)


@router.post("/workbook/commit")
async def workbook_commit(
    user: Annotated[dict, Depends(current_user)],
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form()],
    budgetPolicy: Annotated[str, Form()] = "overwrite",
):
    uid = user["id"]
    if budgetPolicy not in ("overwrite", "skip"):
        raise HTTPException(400, "budgetPolicy must be overwrite or skip")
    data = await _read_workbook_upload(file)
    try:
        parsed = parse_workbook(data)
    except WorkbookError as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        raw_mapping = json.loads(mapping)
        marker_map = {str(k): int(v) for k, v in raw_mapping.items()}
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(400, "mapping must be a JSON object of marker -> accountId") from exc
    markers = {row["marker"] for row in parsed["transactions"]}
    missing = sorted(m for m in markers if m not in marker_map)
    if missing:
        raise HTTPException(400, f"unmapped account markers: {missing}")
    c = conn()
    try:
        for account_id in set(marker_map.values()):
            if not _owned_account(c, account_id, uid):
                raise HTTPException(400, f"unknown account: {account_id}")
        result = apply_workbook(c, uid, parsed, marker_map, budgetPolicy)
        c.commit()
        return {**result, "warnings": parsed["warnings"], "errors": parsed["errors"]}
    finally:
        c.close()
