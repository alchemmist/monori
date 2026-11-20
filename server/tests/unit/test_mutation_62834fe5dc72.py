# Copyright (c) 2024 Monori contributors.
"""Tests for json_values.optional_string."""

import pytest

from monori.common.json_values import JsonValue, optional_string


@pytest.mark.parametrize("value", ["hello", "", "0", "false"])
def test_optional_string_returns_string(value: str) -> None:
    """A JSON string is returned unchanged."""
    assert optional_string(value) == value


@pytest.mark.parametrize("value", [None, 1, 0, 1.5, True, False, [], ["a"], {}])
def test_optional_string_returns_none_for_non_string(value: JsonValue) -> None:
    """A JSON non-string value yields None, so the guard must be evaluated."""
    assert optional_string(value) is None
