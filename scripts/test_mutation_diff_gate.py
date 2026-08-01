import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "mutation_diff_gate", Path(__file__).with_name("mutation-diff-gate.py")
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class MutationDiffGateTest(unittest.TestCase):
    def test_parses_mutmut_function_names(self) -> None:
        self.assertEqual(module.mutant_function("app.foo.x_run__mutmut_1"), ("run", None))
        self.assertEqual(
            module.mutant_function("app.foo.ǁAccountǁx_save__mutmut_2"),
            ("save", "Account"),
        )

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

        self.assertEqual(result, {"server/app/example.py": {("save", "Account")}})

    def test_maps_deletion_only_hunks_to_changed_lines(self) -> None:
        diff = """\
diff --git a/server/app/example.py b/server/app/example.py
--- a/server/app/example.py
+++ b/server/app/example.py
@@ -5 +4,0 @@
-    removed = True
"""

        self.assertEqual(module.parse_changed_lines(diff), {"server/app/example.py": {4}})

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

        self.assertEqual(module.parse_changed_lines(diff), {"server/app/example.py": {2, 3}})

    @staticmethod
    def write_meta(path: Path, statuses: dict[str, int]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"exit_code_by_key": statuses}))

    def run_backend_gate(self, root: Path, baseline: Path, *, skip_new_survivors: bool) -> int:
        mutants = root / "mutants"
        self.write_meta(
            mutants / "app/example.py.meta",
            {
                "app.example.x_run__mutmut_1": 1,
                "app.example.x_run__mutmut_2": 0,
            },
        )
        with (
            mock.patch.object(module, "changed_lines", return_value={}),
            mock.patch.object(
                module,
                "changed_functions",
                return_value={"server/app/example.py": {("run", None)}},
            ),
        ):
            result = module.gate_backend(
                mutants,
                baseline,
                root,
                "origin/main",
                50,
                skip_new_survivors,
            )
        return int(result)

    def test_gate_backend_scores_killed_and_survived_mutants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            self.write_meta(
                baseline / "app/example.py.meta",
                {
                    "app.example.x_run__mutmut_1": 1,
                    "app.example.x_run__mutmut_2": 0,
                },
            )

            self.assertEqual(self.run_backend_gate(root, baseline, skip_new_survivors=False), 0)

    def test_gate_backend_rejects_new_survivors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            self.write_meta(
                baseline / "app/example.py.meta",
                {
                    "app.example.x_run__mutmut_1": 1,
                    "app.example.x_run__mutmut_2": 1,
                },
            )

            self.assertEqual(self.run_backend_gate(root, baseline, skip_new_survivors=False), 1)

    def test_gate_backend_allows_survivors_without_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            self.assertEqual(
                self.run_backend_gate(root, root / "missing", skip_new_survivors=True),
                0,
            )

    def test_load_meta_reports_missing_statuses(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".meta") as metadata:
            metadata.write("{}")
            metadata.flush()

            with self.assertRaisesRegex(TypeError, "missing exit_code_by_key"):
                module.load_meta(Path(metadata.name))


if __name__ == "__main__":
    unittest.main()
