import contextlib
import io
import unittest

from object_annotation_gate import (
    Finding,
    added_lines_from_patch,
    changed_lines,
    comment_body,
    parse_command,
    parse_state,
    scan_file,
    state_marker,
)


class ObjectAnnotationGateTest(unittest.TestCase):
    def test_finds_direct_and_nested_annotations(self) -> None:
        source = """\
class Example:
    value: object

def function(value: list[object]) -> object | None:
    local: dict[str, object]
    return value
"""

        findings = scan_file("example.py", source, set(range(1, 20)))

        self.assertEqual([(finding.line, finding.annotation) for finding in findings], [
            (2, "object"),
            (4, "list[object]"),
            (4, "object | None"),
            (5, "dict[str, object]"),
        ])

    def test_ignores_calls_strings_and_comments(self) -> None:
        source = """\
value = object()
text = "object"
# object
"""

        self.assertEqual(scan_file("example.py", source, set(range(1, 10))), [])

    def test_finds_qualified_and_string_annotations(self) -> None:
        source = """\
value: builtins.object
other: "list[object]"
"""

        findings = scan_file("example.py", source, set(range(1, 10)))

        self.assertEqual([(finding.line, finding.annotation) for finding in findings], [
            (1, "builtins.object"),
            (2, "'list[object]'"),
        ])

    def test_invalid_python_is_reported_without_raising(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            findings = scan_file("broken.py", "value: object =", {1})

        self.assertEqual(findings, [])
        self.assertIn("Cannot parse Python file", output.getvalue())

    def test_approval_state_requires_valid_current_sha(self) -> None:
        body = state_marker("current", {"abc123"})

        self.assertEqual(parse_state(body, "current"), {"abc123"})
        self.assertEqual(parse_state(body, "old"), set())
        self.assertEqual(
            parse_state("<!-- monori-object-annotation-state: not-json -->", "current"), set()
        )

    def test_approval_command_requires_exactly_one_id(self) -> None:
        self.assertEqual(parse_command("/ignore-object abc123"), ("ignore-object", "abc123"))
        self.assertEqual(parse_command("/ignore-file server/app.py"), ("ignore-file", "server/app.py"))
        self.assertEqual(parse_command("/ignore-all"), ("ignore-all", None))
        self.assertEqual(parse_command("/remove-ignore abc123"), ("remove-ignore", "abc123"))
        self.assertIsNone(parse_command("/ignore-object"))
        self.assertIsNone(parse_command("/ignore-object abc123 extra"))
        self.assertIsNone(parse_command("/ignore-all extra"))

    def test_reports_only_added_lines(self) -> None:
        before = "value: object\n"
        after = "value: object\nother: object\n"

        self.assertEqual(changed_lines(before, after), {2})
        findings = scan_file("example.py", after, changed_lines(before, after))
        self.assertEqual([(finding.line, finding.annotation) for finding in findings], [(2, "object")])

    def test_reads_added_lines_from_unified_patch(self) -> None:
        patch = """\
@@ -1,2 +1,3 @@
 value: str
+other: object
 value2: str
"""

        self.assertEqual(added_lines_from_patch(patch), {2})

    def test_comment_includes_finding_count_and_pr_links(self) -> None:
        finding = Finding("server/app/example.py", 7, 2, "object", "finding-1")

        body = comment_body([finding], "sha", set(), "https://github.com/org/repo/pull/1")

        self.assertIn("annotation check (1)", body)
        self.assertIn("https://github.com/org/repo/pull/1/changes#diff-", body)


if __name__ == "__main__":
    unittest.main()
