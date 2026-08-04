"""Strict JSON value helpers shared by CI integrations."""

from __future__ import annotations

from typing import TypeGuard

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
    """String value for this module."""
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


def optional_string(value: JsonValue) -> str | None:
    """Optional string for this module."""
    return value if isinstance(value, str) else None
