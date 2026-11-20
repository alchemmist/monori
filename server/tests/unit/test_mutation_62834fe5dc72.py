# Copyright (c) 2024 Monori contributors.
"""Tests for json_values.optional_string."""

from monori.common.json_values import optional_string


def test_optional_string_returns_string() -> None:
    """A JSON string is returned unchanged."""
    assert optional_string("hello") == "hello"
