import json
import sqlite3
from collections.abc import Iterable, Mapping
from typing import Annotated, Callable, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass as pydantic_dataclass

from ..auth import current_user
from ..deps import conn
from ..importer import CategoryRule, ImportRow, build_rules, categorize, parse_statement, tx_hash
from ..ingest import commit_rows, existing_hash_counts
from ..transfer_service import detect
from ..workbook.apply import apply_workbook, budget_conflicts
from ..workbook.parser import DEFAULT_CURRENCY, WorkbookError, account_slot, parse_workbook

router = APIRouter(prefix="/api/import", tags=["import"])

# matches the client-side statement file cap (importFile.js) so oversized
# uploads fail the same way whether they arrive via file or paste
MAX_STATEMENT_TEXT = 5_000_000

account_slot_typed = cast(Callable[[Mapping[str, object]], str], account_slot)
parse_workbook_typed = cast(Callable[[bytes], dict[str, object]], parse_workbook)
budget_conflicts_typed = cast(Callable[[sqlite3.Connection, int, list[object]], object], budget_conflicts)
apply_workbook_typed = cast(
    Callable[[sqlite3.Connection, int, dict[str, object], dict[str, int], str], dict[str, object]],
    apply_workbook,
)


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class ImportBody:
    text: str
    account_id: int | None = Field(default=None, alias="accountId")


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class CommitRow:
    date: str
    amount: int
    description: str = ""
    bank_category: str = ""
    mcc: str = ""
    account_id: int | None = Field(default=None, alias="accountId")
    category_id: int | None = Field(default=None, alias="categoryId")


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class CommitBody:
    # Kept as a fallback for older clients that send one account for the whole
    # statement. New clients attach an account to every row, because a CSV can
    # contain operations from several cards.
    rows: list[CommitRow]
    account_id: int | None = Field(default=None, alias="accountId")


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class DuplicateBody:
    rows: list[CommitRow]


def _load_user_rules(c: sqlite3.Connection, uid: int) -> dict[str, list[CategoryRule]]:
    groups = {
        r["id"]: r["kind"]
        for r in c.execute(
            "SELECT g.id, t.type AS kind FROM category_groups g"
            " JOIN category_group_types t ON t.id=g.type_id WHERE g.user_id=?",
            (uid,),
        )
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


def _owned_account(c: sqlite3.Connection, account_id: int | None, uid: int) -> bool:
    return (
        account_id is not None
        and c.execute(
            "SELECT id FROM accounts WHERE id=? AND user_id=?", (account_id, uid)
        ).fetchone()
        is not None
    )


def _validate_import_categories(
    c: sqlite3.Connection, uid: int, rows: list[CommitRow]
) -> None:
    """
    Every manually selected import category must belong to the account owner
    and match the sign of its transaction.
    """
    for row in rows:
        category_id = row.category_id
        if category_id is None:
            continue
        category = c.execute(
            "SELECT t.transaction_sign FROM categories c"
            " JOIN category_groups g ON g.id = c.group_id"
            " JOIN category_group_types t ON t.id=g.type_id"
            " WHERE c.id=? AND g.user_id=?",
            (category_id, uid),
        ).fetchone()
        if category is None:
            raise HTTPException(400, "unknown category")
        if row.amount < 0 and category["transaction_sign"] != -1:
            raise HTTPException(400, "expense transaction requires an expense category")
        if row.amount > 0 and category["transaction_sign"] != 1:
            raise HTTPException(400, "income transaction requires an income category")


def _card_digits(card: object) -> str:
    return "".join(ch for ch in str(card or "") if ch.isdigit())


def _detect_row_accounts(
    c: sqlite3.Connection,
    uid: int,
    rows: list[ImportRow],
    fallback_account_id: int | None = None,
) -> None:
    """Put an account on rows whose card tail belongs to exactly one account."""
    bound: dict[str, set[int]] = {}
    for account in c.execute(
        "SELECT id, card_tails FROM accounts WHERE user_id=? AND archived=0", (uid,)
    ):
        for tail in (account["card_tails"] or "").split(","):
            if tail:
                bound.setdefault(tail, set()).add(cast(int, account["id"]))

    for row in rows:
        digits = _card_digits(row.card)
        matches = [
            tail for tail in bound if digits and (digits.endswith(tail) or tail.endswith(digits))
        ]
        best = max(matches, key=len) if matches else None
        owners = bound.get(best, set()) if best else set()
        # A duplicate binding is deliberately left for the user: choosing an
        # arbitrary account here could silently corrupt the ledger. The fallback
        # only exists for the old one-account preview API; the mixed-CSV UI does
        # not send one and therefore requires a manual choice.
        row.account_id = next(iter(owners)) if len(owners) == 1 else fallback_account_id


def _mark_duplicates(c: sqlite3.Connection, rows: list[ImportRow]) -> None:
    """Mark duplicate rows using each row's currently selected account."""
    existing_by_account: dict[int, dict[str, int]] = {}
    seen_in_batch: dict[tuple[int, str], int] = {}
    for row in rows:
        account_id = row.account_id
        if account_id is None:
            row.duplicate = False
            continue
        existing = existing_by_account.get(account_id)
        if existing is None:
            existing = existing_hash_counts(c, account_id)
            existing_by_account[account_id] = existing
        row.hash = tx_hash(account_id, row.date, row.amount, row.description)
        key = (account_id, row.hash)
        n_batch = seen_in_batch.get(key, 0)
        row.duplicate = existing.get(row.hash, 0) > n_batch
        seen_in_batch[key] = n_batch + 1


@router.post("/preview")
def import_preview(
    body: ImportBody, user: Annotated[dict[str, object], Depends(current_user)]
) -> dict[str, object]:
    uid = cast(int, user["id"])
    if len(body.text) > MAX_STATEMENT_TEXT:
        raise HTTPException(413, "statement is too large")
    c = conn()
    try:
        rows, errors = parse_statement(body.text)
        rules = _load_user_rules(c, uid)
        fallback_account_id = (
            body.account_id if body.account_id is not None and _owned_account(c, body.account_id, uid) else None
        )
        _detect_row_accounts(c, uid, rows, fallback_account_id)
        # commit enforces category direction, so the preview must not propose
        # a category the commit would then reject wholesale
        kinds = {
            r["id"]: r["kind"]
            for r in c.execute(
                "SELECT c.id, t.type AS kind FROM categories c"
                " JOIN category_groups g ON g.id = c.group_id"
                " JOIN category_group_types t ON t.id=g.type_id WHERE g.user_id=?",
                (uid,),
            )
        }
        for row in rows:
            category_id = categorize(row.description, row.amount, rules)
            if category_id is not None:
                expected = "expense" if row.amount < 0 else "income"
                if kinds.get(category_id) != expected:
                    category_id = None
            row.category_id = category_id
        _mark_duplicates(c, rows)
        return {"rows": [row.to_api_dict() for row in rows], "errors": [err.to_api_dict() for err in errors]}
    finally:
        c.close()


@router.post("/duplicates")
def import_duplicates(
    body: DuplicateBody, user: Annotated[dict[str, object], Depends(current_user)]
) -> dict[str, list[bool]]:
    """Re-check preview rows after the user manually changes their accounts."""
    uid = cast(int, user["id"])
    c = conn()
    try:
        rows = [
            ImportRow(
                date=row.date,
                amount=row.amount,
                description=row.description,
                bank_category=row.bank_category,
                mcc=row.mcc,
                card="",
                account_id=row.account_id,
            )
            for row in body.rows
        ]
        for row in rows:
            if row.account_id is not None and not _owned_account(c, row.account_id, uid):
                raise HTTPException(400, "unknown account")
        _mark_duplicates(c, rows)
        return {"duplicates": [row.duplicate for row in rows]}
    finally:
        c.close()


@router.post("/commit")
def import_commit(
    body: CommitBody, user: Annotated[dict[str, object], Depends(current_user)]
) -> dict[str, int]:
    """
    Server-side dedup: rows whose hash already exists — or repeats within the
    batch — are skipped, so a double-submit can't create duplicates.
    """
    uid = cast(int, user["id"])
    c = conn()
    try:
        if body.account_id is not None and not _owned_account(c, body.account_id, uid):
            raise HTTPException(400, "unknown account")
        _validate_import_categories(c, uid, body.rows)
        grouped: dict[int, list[dict[str, object]]] = {}
        for r in body.rows:
            # A body-level account is the legacy, single-account contract and
            # intentionally takes precedence over preview metadata.
            account_id = body.account_id if body.account_id is not None else r.account_id
            if account_id is None:
                raise HTTPException(400, "every import row needs an account")
            grouped.setdefault(account_id, []).append(
                {
                    "date": r.date,
                    "amount": r.amount,
                    "description": r.description,
                    "bank_category": r.bank_category,
                    "mcc": r.mcc,
                    "category_id": r.category_id,
                }
            )
        for account_id in grouped:
            if not _owned_account(c, account_id, uid):
                raise HTTPException(400, "unknown account")
        inserted = skipped = 0
        for account_id, rows in grouped.items():
            added, ignored = commit_rows(c, account_id, rows, source="import")
            inserted += added
            skipped += ignored
        merged, suggested = detect(c, uid)
        c.commit()
        return {
            "inserted": inserted,
            "skipped": skipped,
            "transfersMerged": len(merged),
            "transfersSuggested": len(suggested),
        }
    finally:
        c.close()


async def _read_workbook_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    return data


def _account_slots(transactions: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """
    What the user has to map: one entry per card marker per currency. Splitting
    by currency is what makes a foreign-currency migration impossible to get
    wrong — a USD slot can only be pointed at a USD account, so a user without
    one has nothing to pick and the import stays blocked until they make it.
    """
    slots: dict[str, dict[str, object]] = {}
    for row in transactions:
        key = account_slot_typed(row)
        slot = slots.setdefault(
            key,
            {
                "key": key,
                "marker": row["marker"],
                "currency": row.get("currency") or DEFAULT_CURRENCY,
                "transactions": 0,
            },
        )
        slot["transactions"] = cast(int, slot["transactions"]) + 1
    return sorted(slots.values(), key=lambda s: (cast(str, s["currency"]), cast(str, s["marker"])))


def _workbook_preview_summary(parsed: Mapping[str, object]) -> dict[str, object]:
    tx = cast(list[Mapping[str, object]], parsed["transactions"])
    by_year: dict[str, int] = {}
    for row in tx:
        year = cast(str, row["date"])[:4]
        by_year[year] = by_year.get(year, 0) + 1
    return {
        "groups": len(cast(list[object], parsed["groups"])),
        "categories": len(cast(list[object], parsed["categories"])),
        "transactions": len(tx),
        "transactionsByYear": dict(sorted(by_year.items())),
        "budgetCells": len(cast(list[object], parsed["budgets"])),
        "accountSlots": _account_slots(tx),
        "warnings": cast(list[object], parsed["warnings"]),
        "errors": cast(list[object], parsed["errors"]),
    }


def _parse_or_400(data: bytes) -> dict[str, object]:
    try:
        return parse_workbook_typed(data)
    except WorkbookError as exc:
        raise HTTPException(400, str(exc)) from exc


def _preview_workbook(data: bytes, uid: int) -> dict[str, object]:
    parsed = _parse_or_400(data)
    summary = _workbook_preview_summary(parsed)
    c = conn()
    try:
        summary["budgetConflicts"] = budget_conflicts_typed(c, uid, cast(list[object], parsed["budgets"]))
    finally:
        c.close()
    return summary


def _reject_currency_mismatch(
    c: sqlite3.Connection,
    slots: Mapping[str, Mapping[str, object]],
    marker_map: Mapping[str, int],
) -> None:
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
        # only "?" marks are interpolated; the values go through bind params
        for r in c.execute(
            f"SELECT id, currency FROM accounts WHERE id IN ({placeholders})",  # nosec B608
            ids,
        )
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


def _remember_markers(
    c: sqlite3.Connection,
    slots: Mapping[str, Mapping[str, object]],
    marker_map: Mapping[str, int],
) -> int:
    """
    Bind each slot's card marker to the account it was mapped onto, so the next
    statement import or sync routes those cards without asking. Tails are only
    appended — whatever the account already has stays, and a marker with no
    digits (the unmarked-rows slot) binds nothing.
    """
    bound = 0
    for key, slot in slots.items():
        digits = "".join(ch for ch in cast(str, slot["marker"]) if ch.isdigit())
        if not digits or len(digits) > 8:
            continue
        account_id = marker_map[key]
        row = c.execute("SELECT card_tails FROM accounts WHERE id=?", (account_id,)).fetchone()
        tails = [t for t in (cast(str, row["card_tails"]) if row["card_tails"] is not None else "").split(",") if t]
        if digits in tails:
            continue
        tails.append(digits)
        c.execute("UPDATE accounts SET card_tails=? WHERE id=?", (",".join(tails), account_id))
        bound += 1
    return bound


def _commit_workbook(
    data: bytes, uid: int, mapping: str, budget_policy: str, remember: bool
) -> dict[str, object]:
    parsed = _parse_or_400(data)
    try:
        raw_mapping = json.loads(mapping)
        marker_map = {str(k): int(v) for k, v in raw_mapping.items()}
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(400, "mapping must be a JSON object of slot -> accountId") from exc
    slots = {cast(str, s["key"]): s for s in _account_slots(cast(list[Mapping[str, object]], parsed["transactions"]))}
    missing = sorted(k for k in slots if k not in marker_map)
    if missing:
        raise HTTPException(400, f"unmapped account slots: {missing}")
    c = conn()
    try:
        for account_id in set(marker_map.values()):
            if not _owned_account(c, account_id, uid):
                raise HTTPException(400, f"unknown account: {account_id}")
        _reject_currency_mismatch(c, slots, marker_map)
        result = apply_workbook_typed(c, uid, parsed, marker_map, budget_policy)
        result["cardTailsBound"] = _remember_markers(c, slots, marker_map) if remember else 0
        c.commit()
        warnings = [*cast(list[object], parsed["warnings"]), *cast(list[object], result.pop("warnings", []))]
        return {**result, "warnings": warnings, "errors": cast(list[object], parsed["errors"])}
    finally:
        c.close()


# Parsing a workbook and writing thousands of rows takes tens of seconds. Run it
# on a worker thread: on the event loop it would freeze every other request for
# the whole migration, and it opens its own connection there because a sqlite3
# handle belongs to the thread that created it.
@router.post("/workbook/preview")
async def workbook_preview(
    user: Annotated[dict[str, object], Depends(current_user)],
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    data = await _read_workbook_upload(file)
    return await run_in_threadpool(_preview_workbook, data, cast(int, user["id"]))


@router.post("/workbook/commit")
async def workbook_commit(
    user: Annotated[dict[str, object], Depends(current_user)],
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form()],
    budgetPolicy: Annotated[str, Form()] = "overwrite",
    remember: Annotated[bool, Form()] = False,
) -> dict[str, object]:
    if budgetPolicy not in ("overwrite", "skip"):
        raise HTTPException(400, "budgetPolicy must be overwrite or skip")
    data = await _read_workbook_upload(file)
    return await run_in_threadpool(
        _commit_workbook, data, cast(int, user["id"]), mapping, budgetPolicy, remember
    )
