import contextlib
import io
import unittest
from typing import override

from monori.ci.lib.github import sync_label
from monori.ci.quality_graph.checks.object_annotations import (
    FAILURE_LABEL,
    Finding,
    ObjectAnnotationCheck,
    SyncApprovalCommandState,
    added_lines_from_patch,
    changed_lines,
    latest_pull_request_run,
    scan_file,
    summary_body,
    sync_approvals,
)
from monori.ci.quality_graph.commands import parse_command
from monori.ci.quality_graph.models import CheckContext, Verdict
from monori.common import JsonValue


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
        _ = path, ref
        return None

    def ensure_label(self, name: str) -> None:
        self.calls.append(("ensure_label", name, None))

    def is_admin(self, login: str) -> bool:
        _ = login
        return self.permission == "admin"

    def sync_label(self, number: int, name: str, *, present: bool) -> None:
        if present:
            self.ensure_label(name)
            self.request("POST", f"/issues/{number}/labels", {"labels": [name]})
        else:
            self.request("DELETE", f"/issues/{number}/labels/{name}")


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

    def test_admin_approval_uses_stable_labels_and_removes_stale_labels(self) -> None:
        github = FakeGitHub()
        finding = Finding("example.py", 1, 7, "object", "finding-1")

        approved, admin, changed = sync_approvals(
            github,
            1,
            {"body": ""},
            [finding],
            SyncApprovalCommandState(
                parse_command("/qg ignore object-finding-1"),
                "admin",
            ),
        )

        assert admin
        assert changed
        assert approved == {"finding-1"}
        assert any(call[0] == "DELETE" and "stale" in call[1] for call in github.calls)
        assert any(call[0] == "PATCH" and call[1] == "/pulls/1" for call in github.calls)

    def test_failure_label_tracks_active_findings(self) -> None:
        github = FakeGitHub()

        sync_label(github, 1, FAILURE_LABEL, present=True)
        sync_label(github, 1, FAILURE_LABEL, present=False)

        assert (
            "POST",
            "/labels",
            {"name": "monori-object-annotation-failed", "color": "b60205"},
        ) in github.calls
        assert any(call[0] == "DELETE" and "failed" in call[1] for call in github.calls)

    def test_rerun_lookup_paginates_past_first_page(self) -> None:
        class WorkflowRunsGitHub(FakeGitHub):
            @override
            def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
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

        assert run is not None
        assert run["id"] == 999
        assert any("page=2" in call[1] for call in github.calls)

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
