"""Strict JSON value helpers shared by CI integrations."""

from __future__ import annotations

from typing import TypeGuard

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
JsonObject = dict[str, JsonValue]


def is_object(value: JsonValue) -> TypeGuard[JsonObject]:
    return isinstance(value, dict)


def object_value(value: JsonValue, context: str) -> JsonObject:
    if not is_object(value):
        raise TypeError(f"Expected JSON object for {context}")
    return value


def array_value(value: JsonValue, context: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError(f"Expected JSON array for {context}")
    return value


def string_value(value: JsonValue, context: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"Expected JSON string for {context}")
    return value


def integer_value(value: JsonValue, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Expected JSON integer for {context}")
    return value


def optional_string(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None
