"""Validated date and money types shared by persistence boundaries."""

import re
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, Field

MAX_MONEY = 2**53 - 1
Money = Annotated[int, Field(ge=-MAX_MONEY, le=MAX_MONEY)]

DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?)?$"
)
DATE_FORMAT_ERROR = "date must be ISO 8601"
DATE_VALUE_ERROR = "date must be a valid ISO 8601 calendar date"


def validate_transaction_date(value: str) -> str:
    """Accept only real calendar dates in the supported ISO representation."""
    if not DATE_PATTERN.fullmatch(value):
        raise ValueError(DATE_FORMAT_ERROR)
    try:
        if "T" in value:
            datetime.fromisoformat(value)
        else:
            date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(DATE_VALUE_ERROR) from error
    return value


TransactionDate = Annotated[str, AfterValidator(validate_transaction_date)]
