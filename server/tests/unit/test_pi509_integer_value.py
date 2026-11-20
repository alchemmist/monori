# Copyright (c) 2026
"""Regression test for `integer_value` (#509)."""

import pytest

from monori.common.json_values import integer_value


def test_integer_value_rejects_bool_and_non_integer() -> None:
    for value in (True, False, 3.0, None):
        with pytest.raises(TypeError, match=r"^Expected JSON integer for ctx$"):
            integer_value(value, "ctx")
    assert integer_value(3, "ctx") == 3
