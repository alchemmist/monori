"""
Bank statement parsing and auto-categorization.

The paste format is the bank's statement export: one transaction per line,
tab- or semicolon-separated, dates as dd.mm.yyyy [hh:mm:ss], decimal commas.
Categorization is a faithful port of the sheet's FIND_CATEGORIES: rules are
split into IN/OUT by category-group kind, the transaction sign picks the rule
set, and the first category (in definition order) whose keyword is a
case-insensitive substring of the description wins.
"""

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from datetime import datetime
from typing import Literal, overload

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from .connectors.base import SyncRow

type ImportValue = str | int | bool | None
type RuleValue = str | list[str] | int


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class CategoryDefinition:
    """Represent CategoryDefinition."""

    id: int
    name: str
    keywords: str | None
    group_id: int


COLUMNS = [
    "op_date",
    "pay_date",
    "card",
    "status",
    "op_amount",
    "op_currency",
    "amount",
    "currency",
    "cashback",
    "bank_category",
    "mcc",
    "description",
    "bonuses",
    "rounding",
    "rounded_total",
]

DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?$")


HEADER_FIRST_CELLS = {"дата операции", "op_date", "date"}


def _attr_name(key: str) -> str:
    return {
        "accountId": "account_id",
        "categoryId": "category_id",
    }.get(key, key)


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class ParseError:
    """Represent ParseError."""

    line: int
    error: str
    raw: str

    @overload
    def __getitem__(self, key: Literal["line"]) -> int: ...

    @overload
    def __getitem__(self, key: Literal["error"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["raw"]) -> str: ...

    def __getitem__(self, key: str) -> int | str:
        if key == "line":
            return self.line
        if key == "error":
            return self.error
        if key == "raw":
            return self.raw
        raise KeyError(key)

    def to_api_dict(self) -> dict[str, int | str]:
        """Handle to api dict."""
        return asdict(self)


@pydantic_dataclass(config=ConfigDict(extra="forbid", validate_assignment=True))
class ImportRow:
    """Represent ImportRow."""

    date: str
    amount: int
    description: str
    bank_category: str
    mcc: str
    card: str
    account_id: int | None = None
    category_id: int | None = None
    duplicate: bool = False
    hash: str = ""

    @overload
    def __getitem__(self, key: Literal["date"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["amount"]) -> int: ...

    @overload
    def __getitem__(self, key: Literal["description"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["bank_category"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["mcc"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["card"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["accountId"]) -> int | None: ...

    @overload
    def __getitem__(self, key: Literal["categoryId"]) -> int | None: ...

    @overload
    def __getitem__(self, key: Literal["duplicate"]) -> bool: ...

    @overload
    def __getitem__(self, key: Literal["hash"]) -> str: ...

    def __getitem__(self, key: str) -> ImportValue:
        values: dict[str, ImportValue] = self.to_api_dict()
        try:
            return values[key]
        except KeyError:
            snake_key = _attr_name(key)
            if snake_key == "account_id":
                return self.account_id
            if snake_key == "category_id":
                return self.category_id
            raise

    @overload
    def __setitem__(self, key: Literal["accountId"], value: int | None) -> None: ...

    @overload
    def __setitem__(self, key: Literal["categoryId"], value: int | None) -> None: ...

    @overload
    def __setitem__(self, key: Literal["duplicate"], value: bool) -> None: ...

    @overload
    def __setitem__(self, key: Literal["hash"], value: str) -> None: ...

    def __setitem__(self, key: str, value: ImportValue) -> None:
        setattr(self, _attr_name(key), value)

    def get(self, key: str, default: ImportValue = None) -> ImportValue:
        """Handle get."""
        try:
            values: dict[str, ImportValue] = self.to_api_dict()
            return values[key]
        except KeyError:
            return default

    def to_api_dict(self) -> dict[str, ImportValue]:
        """Handle to api dict."""
        return {
            "date": self.date,
            "amount": self.amount,
            "description": self.description,
            "bank_category": self.bank_category,
            "mcc": self.mcc,
            "card": self.card,
            "accountId": self.account_id,
            "categoryId": self.category_id,
            "duplicate": self.duplicate,
            "hash": self.hash,
        }

    def to_ingest_dict(self) -> dict[str, ImportValue]:
        """Serialize at the SQLite ingest boundary, which uses snake_case keys."""
        return {
            "date": self.date,
            "amount": self.amount,
            "description": self.description,
            "bank_category": self.bank_category,
            "mcc": self.mcc,
            "category_id": self.category_id,
        }

    def to_sync_dict(self) -> SyncRow:
        """Handle to sync dict."""
        return SyncRow(
            date=self.date,
            amount=self.amount,
            description=self.description,
            bank_category=self.bank_category,
            mcc=self.mcc,
            card=self.card,
            account_id=self.account_id,
            category_id=self.category_id,
            duplicate=self.duplicate,
            hash=self.hash,
        )


@pydantic_dataclass(config=ConfigDict(extra="forbid"))
class CategoryRule:
    """Represent CategoryRule."""

    category_id: int
    name: str
    keywords: list[str]

    @overload
    def __getitem__(self, key: Literal["category_id"]) -> int: ...

    @overload
    def __getitem__(self, key: Literal["name"]) -> str: ...

    @overload
    def __getitem__(self, key: Literal["keywords"]) -> list[str]: ...

    def __getitem__(self, key: str) -> RuleValue:
        if key == "category_id":
            return self.category_id
        if key == "name":
            return self.name
        if key == "keywords":
            return self.keywords
        raise KeyError(key)


def parse_date(raw: str) -> datetime | None:
    """Handle parse date."""
    m = DATE_RE.match(raw.strip())
    if not m:
        return None
    d, mo, y, hh, mm, ss = m.groups()
    return datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0))  # noqa: DTZ001


def parse_amount_kop(raw: str) -> int | None:
    """'-1 500,00' -> -150000 kopecks."""
    s = str(raw).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not s or s in ("-", "."):
        return None
    try:
        return round(round(float(s), 2) * 100)
    except ValueError:
        return None


def tx_hash(account_id: int, date_iso: str, amount_kop: int, description: str) -> str:
    """
    Dedup key of a transaction. Always scoped to the account: the same.

    date/amount/description legitimately occurs on two different accounts.
    (transfer legs, mirrored cards) and must not collide.
    """
    return hashlib.sha256(
        f"{account_id}|{date_iso}|{amount_kop}|{description}".encode(),
    ).hexdigest()


def parse_statement(text: str) -> tuple[list[ImportRow], list[ParseError]]:
    """
    Handle Returns (rows, errors). Each row: dict with date (ISO), amount (kopecks),.

    description, bank_category, mcc. Accepts both pasted statement rows and a.
    full bank CSV export — a header row is skipped, not reported. Hashes are
    not computed here — the account is not known yet; ingestion derives the
    account-scoped hash on insert.
    """
    rows: list[ImportRow] = []
    errors: list[ParseError] = []
    for ln, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        delim = "\t" if "\t" in line else ";"
        parts = [p.strip().strip('"') for p in line.split(delim)]
        if parts and parts[0].lower() in HEADER_FIRST_CELLS:
            continue
        if len(parts) < 12:  # noqa: PLR2004
            errors.append(ParseError(ln, f"expected >=12 columns, got {len(parts)}", line[:200]))
            continue
        rec = dict(zip(COLUMNS, parts + [""] * (len(COLUMNS) - len(parts)), strict=False))
        date = parse_date(rec["op_date"])
        amount = parse_amount_kop(rec["amount"])
        if date is None or amount is None:
            errors.append(ParseError(ln, "unparseable date or amount", line[:200]))
            continue
        if rec["status"] and rec["status"].upper() == "FAILED":
            continue
        date_iso = date.strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(
            ImportRow(
                date=date_iso,
                amount=amount,
                description=rec["description"],
                bank_category=rec["bank_category"],
                mcc=rec["mcc"],
                card=rec["card"],
            ),
        )
    return rows, errors


def build_rules(
    categories: Iterable[CategoryDefinition],
    groups: Mapping[int, str],
) -> dict[str, list[CategoryRule]]:
    """
    categories: iterable of dicts with name/keywords/group_id;.

    groups: id -> kind ('income'|'expense'). Returns {'IN': [...], 'OUT': [...]}.
    """
    rules: dict[str, list[CategoryRule]] = {"IN": [], "OUT": []}
    for c in categories:
        keywords = [k.strip().lower() for k in (c.keywords or "").split("|") if k.strip()]
        if not keywords:
            continue
        group_id = c.group_id
        kind = groups.get(group_id)
        if kind not in ("income", "expense"):
            continue
        rules["IN" if kind == "income" else "OUT"].append(
            CategoryRule(
                category_id=c.id,
                name=c.name,
                keywords=keywords,
            ),
        )
    return rules


def categorize(
    description: str,
    amount_kop: int,
    rules: Mapping[str, list[CategoryRule]],
) -> int | None:
    """
    Handle Returns category_id or None.

    An inflow is income first — but a merchant's money coming back is a refund,
    and a refund belongs in the envelope it left, or the category quietly reads
    as more spent than it was. So a positive amount that matches no income
    keyword still gets to match the expense keywords.
    """
    desc = description.lower()
    if not desc or amount_kop == 0:
        return None
    for side in ("IN", "OUT") if amount_kop > 0 else ("OUT",):
        for rule in rules[side]:
            for kw in rule.keywords:
                if kw in desc:
                    return rule.category_id
    return None
