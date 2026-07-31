"""Typed domain models shared by workbook parsing, preview and persistence."""

from typing import Literal

from pydantic import ConfigDict, TypeAdapter
from pydantic.dataclasses import dataclass as pydantic_dataclass

_CONFIG = ConfigDict(extra="forbid", frozen=True)


@pydantic_dataclass(config=_CONFIG)
class WorkbookGroup:
    name: str
    sort: int
    kind: Literal["income", "expense"]


@pydantic_dataclass(config=_CONFIG)
class WorkbookCategory:
    group: str
    name: str
    group_kind: Literal["income", "expense"] | None = None
    group_sort: int = 0
    keywords: str = ""


@pydantic_dataclass(config=_CONFIG)
class WorkbookTransaction:
    date: str
    amount: int
    description: str
    currency: str
    bank_category: str = ""
    mcc: str = ""
    comment: str = ""
    monori_category: str = ""
    marker: str = ""


@pydantic_dataclass(config=_CONFIG)
class WorkbookBudget:
    category: str
    year: int
    month: int
    amount: int


@pydantic_dataclass(config=_CONFIG)
class WorkbookParseError:
    row: int
    error: str


@pydantic_dataclass(config=_CONFIG)
class ParsedWorkbook:
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
    key: str
    marker: str
    currency: str
    transactions: int

    def to_api_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "marker": self.marker,
            "currency": self.currency,
            "transactions": self.transactions,
        }


@pydantic_dataclass(config=_CONFIG)
class WorkbookBatchResult:
    account_id: int
    batch_id: int
    inserted: int

    def to_api_dict(self) -> dict[str, object]:
        return {"accountId": self.account_id, "batchId": self.batch_id, "inserted": self.inserted}


@pydantic_dataclass(config=_CONFIG)
class WorkbookApplyResult:
    groups_created: int
    categories_created: int
    inserted: int
    skipped: int
    batches: list[WorkbookBatchResult]
    budgets_written: int
    budgets_skipped: int
    warnings: list[str]

    def to_api_dict(self) -> dict[str, object]:
        return {
            "groupsCreated": self.groups_created,
            "categoriesCreated": self.categories_created,
            "inserted": self.inserted,
            "skipped": self.skipped,
            "batches": [batch.to_api_dict() for batch in self.batches],
            "budgetsWritten": self.budgets_written,
            "budgetsSkipped": self.budgets_skipped,
            "warnings": list(self.warnings),
        }
