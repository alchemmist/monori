import contextlib
import io

import pytest

from monori.ci.quality_graph.checks.object_annotations import (
    Finding,
    ObjectAnnotationCheck,
    added_lines_from_patch,
    changed_lines,
    scan_file,
    summary_body,
)
from monori.ci.quality_graph.job_results import JobControl
from monori.ci.quality_graph.models import CheckContext, Verdict


class TestObjectAnnotationGate:
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

    def test_malformed_hunk_is_rejected(self) -> None:
        with pytest.raises(RuntimeError, match="Cannot parse diff hunk"):
            added_lines_from_patch("@@ malformed @@\n+value: object")

    def test_invalid_forward_reference_is_ignored(self) -> None:
        assert scan_file("example.py", 'value: "list["\n', {1}) == []

    def test_summary_includes_status_and_finding_links_without_admin_commands(
        self,
    ) -> None:
        finding = Finding("server/app/example.py", 7, 2, "object", "finding-1")

        report = summary_body([finding], set(), "https://github.com/org/repo/pull/1")
        body = report.summary

        assert body.startswith("## ❌ Python object annotation gate\n")
        assert "| Status | FAIL |" in body
        assert "| Findings | 1 |" in body
        assert "server/app/example.py:7" in body
        assert "/qg ignore object" in body
        assert report.controls == (
            JobControl(
                "/qg ignore object-finding-1",
                "/qg remove-ignore object-finding-1",
            ),
            JobControl(
                "/qg ignore object-annotations",
                "/qg remove-ignore object-finding-1",
            ),
            JobControl(
                "/qg ignore-file server/app/example.py",
                "/qg remove-ignore object-finding-1",
            ),
        )

    def test_summary_renders_an_approved_finding_as_passed(self) -> None:
        """Keep approved object annotations visible and reversible."""
        finding = Finding("server/app/example.py", 7, 2, "object", "finding-1")

        report = summary_body(
            [finding],
            {finding.finding_id},
            "https://github.com/org/repo/pull/1",
        )
        body = report.summary

        assert body.startswith("## ✅ Python object annotation gate\n")
        assert "| Status | PASS |\n| Findings | 1 |\n| Active | 0 |\n| Approved | 1 |" in body
        assert "- ✔ [`server/app/example.py:7`]" in body
        assert report.controls == (
            JobControl(
                "/qg ignore object-finding-1",
                "/qg remove-ignore object-finding-1",
                checked=True,
            ),
        )
