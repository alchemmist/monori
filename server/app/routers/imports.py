"""Provide backend functionality."""

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import ConfigDict, Field, ValidationError
from pydantic.dataclasses import dataclass as pydantic_dataclass

from app.auth import AuthenticatedUser, current_user
from app.connectors.base import SyncRow
from app.deps import conn
from app.importer import (
    CategoryDefinition,
    CategoryRule,
    ImportRow,
    ParseError,
    build_rules,
    categorize,
    parse_statement,
    tx_hash,
)
from app.ingest import commit_rows, existing_hash_counts
from app.transfer_service import detect
from app.workbook.apply import apply_workbook, budget_conflicts
from app.workbook.models import (
    ACCOUNT_MAPPING_ADAPTER,
    ParsedWorkbook,
    WorkbookAccountSlot,
    WorkbookParseError,
    WorkbookTransaction,
)
from app.workbook.parser import DEFAULT_CURRENCY, WorkbookError, account_slot, parse_workbook

router = APIRouter(prefix="/api/import", tags=["import"])


MAX_STATEMENT_TEXT = 5_000_000


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class ImportBody:
    """Represent ImportBody."""

    text: str
    account_id: int | None = Field(default=None, alias="accountId")


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class CommitRow:
    """Represent CommitRow."""

    date: str
    amount: int
    description: str = ""
    bank_category: str = ""
    mcc: str = ""
    account_id: int | None = Field(default=None, alias="accountId")
    category_id: int | None = Field(default=None, alias="categoryId")


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class CommitBody:
    """Represent CommitBody."""

    rows: list[CommitRow]
    account_id: int | None = Field(default=None, alias="accountId")


@pydantic_dataclass(config=ConfigDict(populate_by_name=True))
class DuplicateBody:
    """Represent DuplicateBody."""

    rows: list[CommitRow]


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class ImportRowResponse:
    """Represent ImportRowResponse."""

    date: str
    amount: int
    description: str
    bank_category: str
    mcc: str
    card: str
    accountId: int | None
    categoryId: int | None
    duplicate: bool
    hash: str


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class ParseErrorResponse:
    """Represent ParseErrorResponse."""

    line: int
    error: str
    raw: str


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class ImportPreviewResponse:
    """Represent ImportPreviewResponse."""

    rows: list[ImportRowResponse]
    errors: list[ParseErrorResponse]


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class DuplicatesResponse:
    """Represent DuplicatesResponse."""

    duplicates: list[bool]


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class ImportCommitResponse:
    """Represent ImportCommitResponse."""

    inserted: int
    skipped: int
    transfersMerged: int
    transfersSuggested: int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class WorkbookAccountSlotResponse:
    """Represent WorkbookAccountSlotResponse."""

    key: str
    marker: str
    currency: str
    transactions: int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class WorkbookParseErrorResponse:
    """Represent WorkbookParseErrorResponse."""

    row: int
    error: str


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class WorkbookPreviewResponse:
    """Represent WorkbookPreviewResponse."""

    groups: int
    categories: int
    transactions: int
    transactionsByYear: dict[str, int]
    budgetCells: int
    accountSlots: list[WorkbookAccountSlotResponse]
    warnings: list[str]
    errors: list[WorkbookParseErrorResponse]
    budgetConflicts: int = 0


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class WorkbookBatchResponse:
    """Represent WorkbookBatchResponse."""

    accountId: int
    batchId: int
    inserted: int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class WorkbookCommitResponse:
    """Represent WorkbookCommitResponse."""

    groupsCreated: int
    categoriesCreated: int
    inserted: int
    skipped: int
    batches: list[WorkbookBatchResponse]
    budgetsWritten: int
    budgetsSkipped: int
    warnings: list[str]
    errors: list[WorkbookParseErrorResponse]
    cardTailsBound: int


def _serialize_import_row(row: ImportRow) -> ImportRowResponse:
    return ImportRowResponse(
        date=row.date,
        amount=row.amount,
        description=row.description,
        bank_category=row.bank_category,
        mcc=row.mcc,
        card=row.card,
        accountId=row.account_id,
        categoryId=row.category_id,
        duplicate=row.duplicate,
        hash=row.hash,
    )


def _serialize_parse_error(error: ParseError) -> ParseErrorResponse:
    return ParseErrorResponse(line=error.line, error=error.error, raw=error.raw)


def _serialize_workbook_error(error: WorkbookParseError) -> WorkbookParseErrorResponse:
    return WorkbookParseErrorResponse(row=error.row, error=error.error)


def _load_user_rules(c: sqlite3.Connection, uid: int) -> dict[str, list[CategoryRule]]:
    groups = {
        r["id"]: r["kind"]
        for r in c.execute(
            "SELECT g.id, t.type AS kind FROM category_groups g"
            " JOIN category_group_types t ON t.id=g.type_id WHERE g.user_id=?",
            (uid,),
        )
    }
    cats: list[CategoryDefinition] = [
        CategoryDefinition(
            id=int(r["id"]),
            name=str(r["name"]),
            keywords=str(r["keywords"]) if r["keywords"] is not None else None,
            group_id=int(r["group_id"]),
        )
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
            "SELECT id FROM accounts WHERE id=? AND user_id=?",
            (account_id, uid),
        ).fetchone()
        is not None
    )


def _validate_import_categories(c: sqlite3.Connection, uid: int, rows: list[CommitRow]) -> None:
    """Every manually selected import category must belong to the account owner.

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


def _card_digits(card: str) -> str:
    return "".join(ch for ch in card if ch.isdigit())


def _detect_row_accounts(
    c: sqlite3.Connection,
    uid: int,
    rows: list[ImportRow],
    fallback_account_id: int | None = None,
) -> None:
    """Put an account on rows whose card tail belongs to exactly one account."""
    bound: dict[str, set[int]] = {}
    for account in c.execute(
        "SELECT id, card_tails FROM accounts WHERE user_id=? AND archived=0",
        (uid,),
    ):
        for tail in (account["card_tails"] or "").split(","):
            if tail:
                account_id = account["id"]
                if not isinstance(account_id, int):
                    msg = "account query returned a non-integer id"
                    raise RuntimeError(msg)
                bound.setdefault(tail, set()).add(account_id)

    for row in rows:
        digits = _card_digits(row.card)
        matches = [
            tail for tail in bound if digits and (digits.endswith(tail) or tail.endswith(digits))
        ]
        best = max(matches, key=len) if matches else None
        owners = bound.get(best, set()) if best else set()

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
    body: ImportBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> ImportPreviewResponse:
    """Handle import preview."""
    uid = user.id
    if len(body.text) > MAX_STATEMENT_TEXT:
        raise HTTPException(413, "statement is too large")
    c = conn()
    try:
        rows, errors = parse_statement(body.text)
        rules = _load_user_rules(c, uid)
        fallback_account_id = (
            body.account_id
            if body.account_id is not None and _owned_account(c, body.account_id, uid)
            else None
        )
        _detect_row_accounts(c, uid, rows, fallback_account_id)

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
        return ImportPreviewResponse(
            rows=[_serialize_import_row(row) for row in rows],
            errors=[_serialize_parse_error(error) for error in errors],
        )
    finally:
        c.close()


@router.post("/duplicates")
def import_duplicates(
    body: DuplicateBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> DuplicatesResponse:
    """Re-check preview rows after the user manually changes their accounts."""
    uid = user.id
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
        return DuplicatesResponse(duplicates=[row.duplicate for row in rows])
    finally:
        c.close()


@router.post("/commit")
def import_commit(
    body: CommitBody,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> ImportCommitResponse:
    """Server-side dedup: rows whose hash already exists — or repeats within the.

    batch — are skipped, so a double-submit can't create duplicates.
    """
    uid = user.id
    c = conn()
    try:
        if body.account_id is not None and not _owned_account(c, body.account_id, uid):
            raise HTTPException(400, "unknown account")
        _validate_import_categories(c, uid, body.rows)
        grouped: dict[int, list[SyncRow]] = {}
        for r in body.rows:
            account_id = body.account_id if body.account_id is not None else r.account_id
            if account_id is None:
                raise HTTPException(400, "every import row needs an account")
            grouped.setdefault(account_id, []).append(
                SyncRow(
                    date=r.date,
                    amount=r.amount,
                    description=r.description,
                    bank_category=r.bank_category,
                    mcc=r.mcc,
                    card="",
                    category_id=r.category_id,
                ),
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
        return ImportCommitResponse(
            inserted=inserted,
            skipped=skipped,
            transfersMerged=len(merged),
            transfersSuggested=len(suggested),
        )
    finally:
        c.close()


async def _read_workbook_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    return data


def _account_slots(transactions: Iterable[WorkbookTransaction]) -> list[WorkbookAccountSlot]:
    """Handle What the user has to map: one entry per card marker per currency. Splitting.

    by currency is what makes a foreign-currency migration impossible to get.
    wrong — a USD slot can only be pointed at a USD account, so a user without
    one has nothing to pick and the import stays blocked until they make it.
    """
    slots: dict[str, WorkbookAccountSlot] = {}
    for row in transactions:
        key = account_slot(row)
        previous = slots.get(key)
        slots[key] = WorkbookAccountSlot(
            key=key,
            marker=row.marker,
            currency=row.currency or DEFAULT_CURRENCY,
            transactions=1 if previous is None else previous.transactions + 1,
        )
    return sorted(slots.values(), key=lambda slot: (slot.currency, slot.marker))


def _workbook_preview_summary(
    parsed: ParsedWorkbook,
    conflicts: int = 0,
) -> WorkbookPreviewResponse:
    by_year: dict[str, int] = {}
    for row in parsed.transactions:
        year = row.date[:4]
        by_year[year] = by_year.get(year, 0) + 1
    return WorkbookPreviewResponse(
        groups=len(parsed.groups),
        categories=len(parsed.categories),
        transactions=len(parsed.transactions),
        transactionsByYear=dict(sorted(by_year.items())),
        budgetCells=len(parsed.budgets),
        accountSlots=[
            WorkbookAccountSlotResponse(
                key=slot.key,
                marker=slot.marker,
                currency=slot.currency,
                transactions=slot.transactions,
            )
            for slot in _account_slots(parsed.transactions)
        ],
        warnings=list(parsed.warnings),
        errors=[_serialize_workbook_error(error) for error in parsed.errors],
        budgetConflicts=conflicts,
    )


def _parse_or_400(data: bytes) -> ParsedWorkbook:
    try:
        return parse_workbook(data)
    except WorkbookError as exc:
        raise HTTPException(400, str(exc)) from exc


def _preview_workbook(data: bytes, uid: int) -> WorkbookPreviewResponse:
    parsed = _parse_or_400(data)
    c = conn()
    try:
        conflicts = budget_conflicts(c, uid, parsed.budgets)
    finally:
        c.close()
    return _workbook_preview_summary(parsed, conflicts)


def _reject_currency_mismatch(
    c: sqlite3.Connection,
    slots: Mapping[str, WorkbookAccountSlot],
    marker_map: Mapping[str, int],
) -> None:
    """Handle An amount is only meaningful on an account held in the same currency:.

    putting 95.78 USD on a ruble account would silently record 95 rubles 78.
    kopecks. The UI already only offers matching accounts; this is the same rule
    enforced where it cannot be clicked around.
    """
    ids = sorted(set(marker_map.values()))
    placeholders = ",".join("?" * len(ids))
    held = {
        r["id"]: (r["currency"] or DEFAULT_CURRENCY).upper()
        for r in c.execute(
            f"SELECT id, currency FROM accounts WHERE id IN ({placeholders})",  # nosec B608  # noqa: S608
            ids,
        )
    }
    for key, slot in slots.items():
        account_id = marker_map[key]
        currency = held.get(account_id, DEFAULT_CURRENCY)
        if currency != slot.currency:
            where = slot.marker or "rows with no card number"
            raise HTTPException(
                400,
                f"{where}: {slot.currency} rows cannot be imported into a"
                f" {currency} account — create an account in {slot.currency} first",
            )


def _remember_markers(
    c: sqlite3.Connection,
    slots: Mapping[str, WorkbookAccountSlot],
    marker_map: Mapping[str, int],
) -> int:
    """Bind each slot's card marker to the account it was mapped onto, so the next.

    statement import or sync routes those cards without asking. Tails are only.
    appended — whatever the account already has stays, and a marker with no
    digits (the unmarked-rows slot) binds nothing.
    """
    bound = 0
    for key, slot in slots.items():
        digits = "".join(ch for ch in slot.marker if ch.isdigit())
        if not digits or len(digits) > 8:  # noqa: PLR2004
            continue
        account_id = marker_map[key]
        row = c.execute("SELECT card_tails FROM accounts WHERE id=?", (account_id,)).fetchone()
        raw_value = row["card_tails"]
        if raw_value is not None and not isinstance(raw_value, str):
            msg = "account query returned non-text card tails"
            raise RuntimeError(msg)
        raw_tails = raw_value or ""
        tails = [tail for tail in raw_tails.split(",") if tail]
        if digits in tails:
            continue
        tails.append(digits)
        c.execute("UPDATE accounts SET card_tails=? WHERE id=?", (",".join(tails), account_id))
        bound += 1
    return bound


def _commit_workbook(
    data: bytes,
    uid: int,
    mapping: str,
    budget_policy: str,
    remember: bool,  # noqa: FBT001
) -> WorkbookCommitResponse:
    parsed = _parse_or_400(data)
    try:
        marker_map = ACCOUNT_MAPPING_ADAPTER.validate_json(mapping)
    except ValidationError as exc:
        raise HTTPException(400, "mapping must be a JSON object of slot -> accountId") from exc
    slots = {slot.key: slot for slot in _account_slots(parsed.transactions)}
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
        card_tails_bound = _remember_markers(c, slots, marker_map) if remember else 0
        c.commit()
        return WorkbookCommitResponse(
            groupsCreated=result.groups_created,
            categoriesCreated=result.categories_created,
            inserted=result.inserted,
            skipped=result.skipped,
            batches=[
                WorkbookBatchResponse(
                    accountId=batch.account_id,
                    batchId=batch.batch_id,
                    inserted=batch.inserted,
                )
                for batch in result.batches
            ],
            budgetsWritten=result.budgets_written,
            budgetsSkipped=result.budgets_skipped,
            warnings=[*parsed.warnings, *result.warnings],
            errors=[_serialize_workbook_error(error) for error in parsed.errors],
            cardTailsBound=card_tails_bound,
        )
    finally:
        c.close()


@router.post("/workbook/preview")
async def workbook_preview(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    file: Annotated[UploadFile, File()],
) -> WorkbookPreviewResponse:
    """Handle workbook preview."""
    data = await _read_workbook_upload(file)
    return await run_in_threadpool(_preview_workbook, data, user.id)


@router.post("/workbook/commit")
async def workbook_commit(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form()],
    budgetPolicy: Annotated[str, Form()] = "overwrite",
    remember: Annotated[bool, Form()] = False,  # noqa: FBT002
) -> WorkbookCommitResponse:
    """Handle workbook commit."""
    if budgetPolicy not in ("overwrite", "skip"):
        raise HTTPException(400, "budgetPolicy must be overwrite or skip")
    data = await _read_workbook_upload(file)
    return await run_in_threadpool(_commit_workbook, data, user.id, mapping, budgetPolicy, remember)
