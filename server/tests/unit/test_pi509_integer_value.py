# Copyright (c) 2026
"""Regression for integer_value rejecting non-integers (mutant x_integer_value__mutmut_1).

The mutant weakens the guard from `isinstance(value, bool) or not isinstance(value, int)`
to `and`, so a non-int value silently passes through instead of raising.
"""

import pytest

from monori.common.json_values import integer_value


@pytest.mark.parametrize("value", [3.5, 3.0, "3", None, [1], {"a": 1}])
def test_integer_value_rejects_non_integers(value: object) -> None:
    with pytest.raises(TypeError, match="Expected JSON integer for ctx"):
        integer_value(value, "ctx")  # type: ignore[arg-type]
