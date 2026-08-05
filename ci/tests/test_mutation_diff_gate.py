import tempfile
import unittest
from pathlib import Path

import pytest

from monori.ci.lib import mutation_diff_gate as module


class MutationDiffGateTest(unittest.TestCase):
    def test_parses_mutmut_function_names(self) -> None:
        assert module.mutant_function("app.foo.x_run__mutmut_1") == ("run", None)
        assert module.mutant_function("app.foo.ǁAccountǁx_save__mutmut_2") == (
            "save",
            "Account",
        )

    def test_maps_mutant_metadata_to_its_configured_source_path(self) -> None:
        assert module.source_path_for_mutant(Path("app/example.py.meta")) == "server/app/example.py"
        assert (
            module.source_path_for_mutant(Path("quality_graph/app/example.py.meta"))
            == "ci/quality_graph/app/example.py"
        )
        assert module.source_path_for_mutant(Path("lib/comments.py.meta")) == "ci/lib/comments.py"

    def test_collects_changed_functions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "server/app/example.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "class Account:\n"
                "    def save(self):\n"
                "        return True\n"
                "\n"
                "def untouched():\n"
                "    return False\n"
            )

            result = module.changed_functions(root, {"server/app/example.py": {3}})

        assert result == {"server/app/example.py": {("save", "Account")}}

    def test_maps_deletion_only_hunks_to_changed_lines(self) -> None:
        diff = """\
diff --git a/server/app/example.py b/server/app/example.py
--- a/server/app/example.py
+++ b/server/app/example.py
@@ -5 +4,0 @@
-    removed = True
"""

        assert module.parse_changed_lines(diff) == {"server/app/example.py": {4}}

    def test_ignores_deleted_file_before_modified_file(self) -> None:
        diff = """\
diff --git a/server/app/deleted.py b/server/app/deleted.py
--- a/server/app/deleted.py
+++ /dev/null
@@ -1 +0,0 @@
-removed = True
diff --git a/server/app/example.py b/server/app/example.py
--- a/server/app/example.py
+++ b/server/app/example.py
@@ -3 +3 @@
-old = True
\\ No newline at end of file
+new = True
\\ No newline at end of file
"""

        assert module.parse_changed_lines(diff) == {"server/app/example.py": {2, 3}}

    def test_load_meta_reports_missing_statuses(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".meta") as metadata:
            metadata.write("{}")
            metadata.flush()

            with pytest.raises(TypeError, match="missing exit_code_by_key"):
                module.load_meta(Path(metadata.name))


if __name__ == "__main__":
    unittest.main()
