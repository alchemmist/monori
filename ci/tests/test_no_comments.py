from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from monori.ci.lib.no_comments import main, violations


class NoCommentsTest(unittest.TestCase):
    def test_rejects_standalone_and_inline_comments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.py"
            path.write_text("# prose\nvalue = 1  # prose\n", encoding="utf-8")
            assert [item[0] for item in violations(path)] == [1, 2]

    def test_allows_functional_directives_and_shebang(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.py"
            path.write_text(
                "#!/usr/bin/env python3\n"
                "value = 1  # noqa: F401\n"
                "other = 2  # nosec B101\n"
                "third = 3  # type: ignore[assignment]\n",
                encoding="utf-8",
            )
            assert violations(path) == []

    def test_hash_in_string_is_not_a_comment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.py"
            path.write_text('value = "# not a comment"\n', encoding="utf-8")
            assert violations(path) == []

    def test_main_reports_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.py"
            path.write_text("value = 1  # prose\n", encoding="utf-8")
            assert main([directory]) == 1

    def test_main_scans_multiple_package_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            first.mkdir()
            second.mkdir()
            (first / "clean.py").write_text("value = 1\n", encoding="utf-8")
            (second / "invalid.py").write_text("value = 2  # prose\n", encoding="utf-8")

            assert main([str(first), str(second)]) == 1


if __name__ == "__main__":
    unittest.main()
