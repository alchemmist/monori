# Copyright (c) 2026
"""
Regression for `integer_value` guarding the JSON integer contract (#509).

The base guard is `isinstance(value, bool) or not isinstance(value, int)`, so
any non-int JSON value (and a bool) must raise a contextual `TypeError`. The
`or`->`and` swap makes the guard nearly never fire: since `bool` is a subclass
of `int`, no value is both a bool and a non-int, so nothing is ever rejected.
Every non-int therefore leaks through unconverted.
"""

import pytest

from monori.common.json_values import JsonValue, integer_value


@pytest.mark.parametrize(
    "value",
    [3.5, 3.0, "3", "", None, [1], {"a": 1}, True, False],
)
def test_integer_value_rejects_non_integers(value: JsonValue) -> None:
    with pytest.raises(TypeError, match=r"^Expected JSON integer for ctx$"):
        integer_value(value, "ctx")


@pytest.mark.parametrize("value", [0, 7, -3, 2**70])
def test_integer_value_accepts_integers(value: int) -> None:
    result = integer_value(value, "ctx")
    assert result == value
    assert isinstance(result, int)


def test_integer_value_error_names_the_context() -> None:
    with pytest.raises(TypeError) as excinfo:
        integer_value("12", "account.sort")
    assert str(excinfo.value) == "Expected JSON integer for account.sort"
