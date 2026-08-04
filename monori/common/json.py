"""Strict JSON value helpers shared by all Monori Python packages."""

from __future__ import annotations

import json
from typing import TypeGuard, cast

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
JsonObject = dict[str, JsonValue]


def is_object(value: JsonValue) -> TypeGuard[JsonObject]:
    """Return whether object."""
    return isinstance(value, dict)


def object_value(value: JsonValue, context: str) -> JsonObject:
    """Object value for this module."""
    if not is_object(value):
        message = f"Expected JSON object for {context}"
        raise TypeError(message)
    return value


def array_value(value: JsonValue, context: str) -> list[JsonValue]:
    """Array value for this module."""
    if not isinstance(value, list):
        message = f"Expected JSON array for {context}"
        raise TypeError(message)
    return value


def string_value(value: JsonValue, context: str) -> str:
    """Return a string JSON value."""
    if not isinstance(value, str):
        message = f"Expected JSON string for {context}"
        raise TypeError(message)
    return value


def integer_value(value: JsonValue, context: str) -> int:
    """Integer value for this module."""
    if isinstance(value, bool) or not isinstance(value, int):
        message = f"Expected JSON integer for {context}"
        raise TypeError(message)
    return value


def number_value(value: JsonValue, context: str) -> int | float:
    """Return a JSON number or raise a contextual type error."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        message = f"Expected JSON number for {context}"
        raise TypeError(message)
    return value


def optional_string(value: JsonValue) -> str | None:
    """Return a JSON string if present."""
    return value if isinstance(value, str) else None


def decode_json(data: bytes | str) -> JsonValue:
    """Decode JSON while preserving the recursive JSON value type."""
    return cast("JsonValue", json.loads(data))
