import importlib.util
import tempfile
import unittest
from pathlib import Path

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
@@ -2,2 +2 @@
     keep = True
-    removed = True
"""

        self.assertEqual(module.parse_changed_lines(diff), {"server/app/example.py": {2}})


if __name__ == "__main__":
    unittest.main()
