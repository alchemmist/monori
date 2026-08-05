import contextlib
import io
import unittest

from monori.ci.quality_graph.checks.object_annotations import (
    Finding,
    ObjectAnnotationCheck,
    added_lines_from_patch,
    changed_lines,
    scan_file,
    summary_body,
)
from monori.ci.quality_graph.commands import parse_command
from monori.ci.quality_graph.models import CheckContext, Verdict


class ObjectAnnotationGateTest(unittest.TestCase):
    def test_check_class_collects_typed_result(self) -> None:
        result = ObjectAnnotationCheck().collect(
            CheckContext(
                files={"example.py": "def f(value: object) -> str:\n    return 'x'\n"},
                changed_lines={"example.py": frozenset({1})},
            )
        )

        assert result.verdict == Verdict.FAIL
        assert len(result.findings) == 1
        assert isinstance(result.findings[0], Finding)

    def test_finds_direct_and_nested_annotations(self) -> None:
        source = """\
class Example:
    value: object

def function(value: list[object]) -> object | None:
    local: dict[str, object]
    return value
"""

        findings = scan_file("example.py", source, set(range(1, 20)))

        assert [(finding.line, finding.annotation) for finding in findings] == [
            (2, "object"),
            (4, "list[object]"),
            (4, "object | None"),
            (5, "dict[str, object]"),
        ]

    def test_ignores_calls_strings_and_comments(self) -> None:
        source = """\
value = object()
text = "object"
# object
"""

        assert scan_file("example.py", source, set(range(1, 10))) == []

    def test_finds_qualified_and_string_annotations(self) -> None:
        source = """\
value: builtins.object
other: "list[object]"
"""

        findings = scan_file("example.py", source, set(range(1, 10)))

        assert [(finding.line, finding.annotation) for finding in findings] == [
            (1, "builtins.object"),
            (2, "'list[object]'"),
        ]

    def test_invalid_python_is_reported_without_raising(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            findings = scan_file("broken.py", "value: object =", {1})

        assert findings == []
        assert "Cannot parse Python file" in output.getvalue()

    def test_finding_id_survives_line_shift_but_not_annotation_change(self) -> None:
        before = scan_file("example.py", "value: object\n", {1})[0]
        after = scan_file("example.py", "header = 0\nvalue: object\n", {2})[0]
        changed = scan_file("example.py", "value: list[object]\n", {1})[0]

        assert before.finding_id == after.finding_id
        assert before.finding_id != changed.finding_id

    def test_approval_commands_use_shared_namespace(self) -> None:
        assert parse_command("/qg ignore object-abc123") is not None
        assert parse_command("/qg ignore-file server/app.py") is not None
        assert parse_command("/qg ignore object-abc123,suppression-def456") is not None
        assert parse_command("/qg remove-ignore object-abc123,suppression-def456") is not None
        assert parse_command("/qg ignore object") == parse_command("/quality-graph ignore object")
        assert parse_command("/ignore object-abc123") is None
        assert parse_command("/qg ignore object-abc123 extra") is None
        assert parse_command("/qg ignore all") is None

    def test_reports_only_added_lines(self) -> None:
        before = "value: object\n"
        after = "value: object\nother: object\n"

        assert changed_lines(before, after) == {2}
        findings = scan_file("example.py", after, changed_lines(before, after))
        assert [(finding.line, finding.annotation) for finding in findings] == [(2, "object")]

    def test_reads_added_lines_from_unified_patch(self) -> None:
        patch = """\
@@ -1,2 +1,3 @@
 value: str
+other: object
 value2: str
"""

        assert added_lines_from_patch(patch) == {2}

    def test_summary_includes_status_and_finding_links_without_admin_commands(
        self,
    ) -> None:
        finding = Finding("server/app/example.py", 7, 2, "object", "finding-1")

        body = summary_body([finding], set(), "https://github.com/org/repo/pull/1")

        assert body.startswith("## ❌ Python object annotation gate\n")
        assert "| Status | FAIL |" in body
        assert "| Findings | 1 |" in body
        assert "server/app/example.py:7" in body
        assert "/qg ignore object" in body


if __name__ == "__main__":
    unittest.main()
