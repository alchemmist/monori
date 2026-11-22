# Copyright (c) 2026

import pytest

from monori.server.app.pg_console import field_names


def test_field_names_extracts_parser_names() -> None:
    assert field_names({"funcname": [{"sval": "count"}]}, "funcname") == ["count"]


@pytest.mark.parametrize(
    "node",
    [
        {},
        {"funcname": None},
        {"funcname": [None]},
        {"funcname": [{"sval": 3}]},
        {"funcname": [{"String": {"sval": "count"}}]},
    ],
)
def test_field_names_rejects_malformed_ast_names(node: dict[str, object]) -> None:
    with pytest.raises(TypeError, match="Invalid PostgreSQL syntax tree"):
        field_names(node, "funcname")
