import contextlib
import io
import unittest
from typing import override

from scripts.object_annotation_gate import (
    Finding,
    JsonValue,
    added_lines_from_patch,
    changed_lines,
    latest_pull_request_run,
    parse_command,
    scan_file,
    summary_body,
    sync_approvals,
    sync_failure_label,
)


class FakeGitHub:
    def __init__(self, permission: str = "admin") -> None:
        self.permission = permission
        self.calls: list[tuple[str, str, JsonValue]] = []

    def paged(self, path: str) -> list[dict[str, JsonValue]]:
        self.calls.append(("paged", path, None))
        return [
            {"name": "monori-object-annotation-ignore-stale"},
            {"name": "monori-object-annotation-ignore-finding-1"},
        ]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        self.calls.append((method, path, payload))
        if path.startswith("/collaborators/"):
            return {"permission": self.permission}
        return None

    def file_text(self, path: str, ref: str) -> str | None:
        return None

    def ensure_label(self, name: str) -> None:
        self.calls.append(("ensure_label", name, None))


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

        self.assertEqual(
            [(finding.line, finding.annotation) for finding in findings],
            [
                (2, "object"),
                (4, "list[object]"),
                (4, "object | None"),
                (5, "dict[str, object]"),
            ],
        )

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

        self.assertEqual(
            [(finding.line, finding.annotation) for finding in findings],
            [
                (1, "builtins.object"),
                (2, "'list[object]'"),
            ],
        )

    def test_invalid_python_is_reported_without_raising(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            findings = scan_file("broken.py", "value: object =", {1})

        self.assertEqual(findings, [])
        self.assertIn("Cannot parse Python file", output.getvalue())

    def test_finding_id_survives_line_shift_but_not_annotation_change(self) -> None:
        before = scan_file("example.py", "value: object\n", {1})[0]
        after = scan_file("example.py", "header = 0\nvalue: object\n", {2})[0]
        changed = scan_file("example.py", "value: list[object]\n", {1})[0]

        self.assertEqual(before.finding_id, after.finding_id)
        self.assertNotEqual(before.finding_id, changed.finding_id)

    def test_admin_approval_uses_stable_labels_and_removes_stale_labels(self) -> None:
        github = FakeGitHub()
        finding = Finding("example.py", 1, 7, "object", "finding-1")

        approved, admin, changed = sync_approvals(
            github,
            1,
            {"body": ""},
            [finding],
            ("ignore", ["object-finding-1"]),
            "admin",
        )

        self.assertTrue(admin)
        self.assertTrue(changed)
        self.assertEqual(approved, {"finding-1"})
        self.assertTrue(
            any(call[0] == "DELETE" and "stale" in call[1] for call in github.calls)
        )
        self.assertTrue(
            any(call[0] == "PATCH" and call[1] == "/pulls/1" for call in github.calls)
        )

    def test_failure_label_tracks_active_findings(self) -> None:
        github = FakeGitHub()

        sync_failure_label(github, 1, True)
        sync_failure_label(github, 1, False)

        self.assertIn(
            ("ensure_label", "monori-object-annotation-failed", None), github.calls
        )
        self.assertTrue(
            any(call[0] == "DELETE" and "failed" in call[1] for call in github.calls)
        )

    def test_rerun_lookup_paginates_past_first_page(self) -> None:
        class WorkflowRunsGitHub(FakeGitHub):
            @override
            def request(
                self, method: str, path: str, payload: JsonValue = None
            ) -> JsonValue:
                self.calls.append((method, path, payload))
                if path.endswith("page=1"):
                    return {
                        "workflow_runs": [
                            {"id": index, "pull_requests": []} for index in range(100)
                        ]
                    }
                return {
                    "workflow_runs": [
                        {
                            "id": 999,
                            "created_at": "2026-01-01",
                            "pull_requests": [{"number": 343}],
                        }
                    ]
                }

        github = WorkflowRunsGitHub()

        run = latest_pull_request_run(github, 343)

        self.assertEqual(run and run["id"], 999)
        self.assertTrue(any("page=2" in call[1] for call in github.calls))

    def test_approval_commands_use_shared_namespace(self) -> None:
        self.assertEqual(
            parse_command("/ignore object-abc123"), ("ignore", ["object-abc123"])
        )
        self.assertEqual(
            parse_command("/ignore-file server/app.py"),
            ("ignore-file", ["server/app.py"]),
        )
        self.assertEqual(
            parse_command("/ignore object-abc123,suppression-def456"),
            ("ignore", ["object-abc123", "suppression-def456"]),
        )
        self.assertEqual(parse_command("/ignore-all"), ("ignore-all", None))
        self.assertEqual(
            parse_command("/remove-ignore object-abc123,suppression-def456"),
            ("remove-ignore", ["object-abc123", "suppression-def456"]),
        )
        self.assertIsNone(parse_command("/ignore"))
        self.assertIsNone(parse_command("/ignore object-abc123 extra"))
        self.assertIsNone(parse_command("/ignore-all extra"))

    def test_reports_only_added_lines(self) -> None:
        before = "value: object\n"
        after = "value: object\nother: object\n"

        self.assertEqual(changed_lines(before, after), {2})
        findings = scan_file("example.py", after, changed_lines(before, after))
        self.assertEqual(
            [(finding.line, finding.annotation) for finding in findings],
            [(2, "object")],
        )

    def test_reads_added_lines_from_unified_patch(self) -> None:
        patch = """\
@@ -1,2 +1,3 @@
 value: str
+other: object
 value2: str
"""

        self.assertEqual(added_lines_from_patch(patch), {2})

    def test_summary_includes_status_and_finding_links_without_admin_commands(
        self,
    ) -> None:
        finding = Finding("server/app/example.py", 7, 2, "object", "finding-1")

        body = summary_body([finding], set(), "https://github.com/org/repo/pull/1")

        self.assertIn("## Python object annotation gate", body)
        self.assertIn("| Status | ❌ FAIL |", body)
        self.assertIn("| Findings | 1 |", body)
        self.assertIn("server/app/example.py:7", body)
        self.assertIn("/ignore-all", body)


if __name__ == "__main__":
    unittest.main()
