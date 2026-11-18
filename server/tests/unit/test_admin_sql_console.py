import time

import pytest

from monori.server.app.routers.admin_sql import BLOB_PREVIEW, cell, leading_keyword


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1", "SELECT"),
        ("  \n\t update users set x=1", "UPDATE"),
        ("-- a note\nDELETE FROM t", "DELETE"),
        ("/* block */ INSERT INTO t VALUES (1)", "INSERT"),
        ("/* one */ -- two\n\n/* three */\nCREATE TABLE t (i)", "CREATE"),
        ("WITH x AS (SELECT 1) SELECT * FROM x", "WITH"),
        ("", ""),
        ("   \n  ", ""),
        ("-- only a comment, never closed", ""),
        ("/* unterminated", ""),
    ],
)
def test_leading_keyword(sql: str, expected: str) -> None:
    assert leading_keyword(sql) == expected


def test_leading_keyword_is_linear_on_adversarial_comment_openings() -> None:

    started = time.perf_counter()
    assert leading_keyword("/* " * 40000) == ""
    assert time.perf_counter() - started < 1.0


def test_cell_passes_scalars_through_and_summarizes_blobs() -> None:
    assert cell(None) is None
    assert cell(42) == 42
    assert cell("text") == "text"
    assert cell(b"\x00\x01") == "x'0001' (2 bytes)"
    long = cell(b"\xab" * (BLOB_PREVIEW + 10))
    assert isinstance(long, str)
    assert long.startswith("x'ab")
    assert long.endswith(f"…' ({BLOB_PREVIEW + 10} bytes)")
