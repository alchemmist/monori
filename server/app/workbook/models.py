"""Typed domain models shared by workbook parsing, preview and persistence."""

from typing import Literal

from pydantic import ConfigDict, TypeAdapter
from pydantic.dataclasses import dataclass as pydantic_dataclass

_CONFIG = ConfigDict(extra="forbid", frozen=True)


@pydantic_dataclass(config=_CONFIG)
class WorkbookGroup:
    """Represent WorkbookGroup."""

    name: str
    sort: int
    kind: Literal["income", "expense"]


@pydantic_dataclass(config=_CONFIG)
class WorkbookCategory:
    """Represent WorkbookCategory."""

    group: str
    name: str
    group_kind: Literal["income", "expense"] | None = None
    group_sort: int = 0
    keywords: str = ""


@pydantic_dataclass(config=_CONFIG)
class WorkbookTransaction:
    """Represent WorkbookTransaction."""

    date: str
    amount: int
    description: str
    currency: str
    bank_category: str = ""
    mcc: str = ""
    comment: str = ""
    monori_category_group: str = ""
    monori_category: str = ""
    marker: str = ""


@pydantic_dataclass(config=_CONFIG)
class WorkbookBudget:
    """Represent WorkbookBudget."""

    category: str
    year: int
    month: int
    amount: int
    group: str = ""


@pydantic_dataclass(config=_CONFIG)
class WorkbookParseError:
    """Represent WorkbookParseError."""

    row: int
    error: str


@pydantic_dataclass(config=_CONFIG)
class ParsedWorkbook:
    """Represent ParsedWorkbook."""

    groups: list[WorkbookGroup]
    categories: list[WorkbookCategory]
    transactions: list[WorkbookTransaction]
    budgets: list[WorkbookBudget]
    warnings: list[str]
    errors: list[WorkbookParseError]


PARSED_WORKBOOK_ADAPTER = TypeAdapter(ParsedWorkbook)
ACCOUNT_MAPPING_ADAPTER = TypeAdapter(dict[str, int])


@pydantic_dataclass(config=_CONFIG)
class WorkbookAccountSlot:
    """Represent WorkbookAccountSlot."""

    key: str
    marker: str
    currency: str
    transactions: int


@pydantic_dataclass(config=_CONFIG)
class WorkbookBatchResult:
    """Represent WorkbookBatchResult."""

    account_id: int
    batch_id: int
    inserted: int


@pydantic_dataclass(config=_CONFIG)
class WorkbookApplyResult:
    """Represent WorkbookApplyResult."""

    groups_created: int
    categories_created: int
    inserted: int
    skipped: int
    batches: list[WorkbookBatchResult]
    budgets_written: int
    budgets_skipped: int
    warnings: list[str]
