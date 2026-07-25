import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..auth import current_user
from ..deps import conn
from ..importer import build_rules, categorize, parse_statement, tx_hash
from ..ingest import commit_rows, existing_hash_counts
from ..workbook.apply import apply_workbook, budget_conflicts
from ..workbook.parser import DEFAULT_CURRENCY, WorkbookError, account_slot, parse_workbook

router = APIRouter(prefix="/api/import", tags=["import"])

# matches the client-side statement file cap (importFile.js) so oversized
# uploads fail the same way whether they arrive via file or paste
MAX_STATEMENT_TEXT = 5_000_000


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
    if len(body.text) > MAX_STATEMENT_TEXT:
        raise HTTPException(413, "statement is too large")
    c = conn()
    try:
        rows, errors = parse_statement(body.text)
        rules = _load_user_rules(c, uid)
        account_id = body.accountId if _owned_account(c, body.accountId, uid) else None
        existing = existing_hash_counts(c, account_id) if account_id is not None else {}
        seen_in_batch: dict = {}
        for row in rows:
            row["categoryId"] = categorize(row["description"], row["amount"], rules)
            if account_id is None:
                # no account to dedup against — don't fabricate account-less hashes
                row["duplicate"] = False
                continue
            row["hash"] = tx_hash(account_id, row["date"], row["amount"], row["description"])
            n_batch = seen_in_batch.get(row["hash"], 0)
            row["duplicate"] = existing.get(row["hash"], 0) > n_batch
            seen_in_batch[row["hash"]] = n_batch + 1
        return {"rows": rows, "errors": errors}
    finally:
        c.close()


@router.post("/commit")
def import_commit(body: CommitBody, user: Annotated[dict, Depends(current_user)]):
    """
    Server-side dedup: rows whose hash already exists — or repeats within the
    batch — are skipped, so a double-submit can't create duplicates.
    """
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
    if not data:
        raise HTTPException(400, "empty upload")
    return data


def _account_slots(transactions):
    """
    What the user has to map: one entry per card marker per currency. Splitting
    by currency is what makes a foreign-currency migration impossible to get
    wrong — a USD slot can only be pointed at a USD account, so a user without
    one has nothing to pick and the import stays blocked until they make it.
    """
    slots: dict[str, dict] = {}
    for row in transactions:
        key = account_slot(row)
        slot = slots.setdefault(
            key,
            {
                "key": key,
                "marker": row["marker"],
                "currency": row.get("currency") or DEFAULT_CURRENCY,
                "transactions": 0,
            },
        )
        slot["transactions"] += 1
    return sorted(slots.values(), key=lambda s: (s["currency"], s["marker"]))


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
        "accountSlots": _account_slots(tx),
        "warnings": parsed["warnings"],
        "errors": parsed["errors"],
    }


def _parse_or_400(data):
    try:
        return parse_workbook(data)
    except WorkbookError as exc:
        raise HTTPException(400, str(exc)) from exc


def _preview_workbook(data, uid):
    parsed = _parse_or_400(data)
    summary = _workbook_preview_summary(parsed)
    c = conn()
    try:
        summary["budgetConflicts"] = budget_conflicts(c, uid, parsed["budgets"])
    finally:
        c.close()
    return summary


def _reject_currency_mismatch(c, slots, marker_map):
    """
    An amount is only meaningful on an account held in the same currency:
    putting 95.78 USD on a ruble account would silently record 95 rubles 78
    kopecks. The UI already only offers matching accounts; this is the same rule
    enforced where it cannot be clicked around.
    """
    ids = sorted(set(marker_map.values()))
    placeholders = ",".join("?" * len(ids))
    held = {
        r["id"]: (r["currency"] or DEFAULT_CURRENCY).upper()
        for r in c.execute(f"SELECT id, currency FROM accounts WHERE id IN ({placeholders})", ids)
    }
    for key, slot in slots.items():
        account_id = marker_map[key]
        currency = held.get(account_id, DEFAULT_CURRENCY)
        if currency != slot["currency"]:
            where = slot["marker"] or "rows with no card number"
            raise HTTPException(
                400,
                f"{where}: {slot['currency']} rows cannot be imported into a"
                f" {currency} account — create an account in {slot['currency']} first",
            )


def _commit_workbook(data, uid, mapping, budget_policy):
    parsed = _parse_or_400(data)
    try:
        raw_mapping = json.loads(mapping)
        marker_map = {str(k): int(v) for k, v in raw_mapping.items()}
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(400, "mapping must be a JSON object of slot -> accountId") from exc
    slots = {s["key"]: s for s in _account_slots(parsed["transactions"])}
    missing = sorted(k for k in slots if k not in marker_map)
    if missing:
        raise HTTPException(400, f"unmapped account slots: {missing}")
    c = conn()
    try:
        for account_id in set(marker_map.values()):
            if not _owned_account(c, account_id, uid):
                raise HTTPException(400, f"unknown account: {account_id}")
        _reject_currency_mismatch(c, slots, marker_map)
        result = apply_workbook(c, uid, parsed, marker_map, budget_policy)
        c.commit()
        warnings = [*parsed["warnings"], *result.pop("warnings", [])]
        return {**result, "warnings": warnings, "errors": parsed["errors"]}
    finally:
        c.close()


# Parsing a workbook and writing thousands of rows takes tens of seconds. Run it
# on a worker thread: on the event loop it would freeze every other request for
# the whole migration, and it opens its own connection there because a sqlite3
# handle belongs to the thread that created it.
@router.post("/workbook/preview")
async def workbook_preview(
    user: Annotated[dict, Depends(current_user)],
    file: Annotated[UploadFile, File()],
):
    data = await _read_workbook_upload(file)
    return await run_in_threadpool(_preview_workbook, data, user["id"])


@router.post("/workbook/commit")
async def workbook_commit(
    user: Annotated[dict, Depends(current_user)],
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form()],
    budgetPolicy: Annotated[str, Form()] = "overwrite",
):
    if budgetPolicy not in ("overwrite", "skip"):
        raise HTTPException(400, "budgetPolicy must be overwrite or skip")
    data = await _read_workbook_upload(file)
    return await run_in_threadpool(_commit_workbook, data, user["id"], mapping, budgetPolicy)
