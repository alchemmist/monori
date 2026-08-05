"""Test the shared approval and gate-state lifecycle."""

import contextlib
import io
import re
from dataclasses import dataclass
from typing import override
from unittest import mock

import pytest

from monori.ci.lib.github import RepositoryGitHubAPI
from monori.ci.quality_graph.base import (
    ApprovalLifecycle,
    ApprovalRequest,
    PullRequestSourceCheck,
    QualityCheck,
)
from monori.ci.quality_graph.commands import encode_command, parse_command
from monori.ci.quality_graph.models import CheckContext, CheckResult, Verdict
from monori.ci.quality_graph.registry import registered_checks
from monori.ci.quality_graph.reporting import PullRequestReport
from monori.common import JsonValue


@dataclass(frozen=True)
class Finding:
    """Provide a minimal finding accepted by the shared lifecycle."""

    path: str
    finding_id: str


class FakeGitHub:
    """Record state changes and expose one collaborator permission."""

    def __init__(
        self,
        permission: str = "admin",
        comments: dict[int, dict[str, JsonValue]] | None = None,
    ) -> None:
        """Initialize the fake with a collaborator permission."""
        self.permission = permission
        self.comments = comments or {}
        self.calls: list[tuple[str, str, JsonValue]] = []

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Record a request and return permission fixture data."""
        self.calls.append((method, path, payload))
        if path.startswith("/collaborators/"):
            return {"permission": self.permission}
        if method == "GET" and path.startswith("/issues/comments/"):
            return self.comments.get(int(path.rsplit("/", maxsplit=1)[1]))
        return None

    def paged(self, path: str) -> list[dict[str, JsonValue]]:
        """Return no paginated fixtures for the shared lifecycle tests."""
        self.calls.append(("paged", path, None))
        return []

    def file_text(self, path: str, ref: str) -> str | None:
        """Return no repository file fixture."""
        self.calls.append(("file_text", f"{path}@{ref}", None))
        return None


LIFECYCLE = ApprovalLifecycle(
    "example",
    "example-",
    re.compile(r"<!-- example-approvals: ([a-z0-9,-]*) -->"),
    "<!-- example-approvals: {ids} -->",
)

PENDING_LIFECYCLE = ApprovalLifecycle(
    "bundle",
    "bundle-",
    re.compile(r"<!-- bundle-approvals: ([a-z0-9,-]*) -->"),
    "<!-- bundle-approvals: {ids} -->",
    re.compile(r"<!-- bundle-pending: (\d+)(?: ([A-Za-z0-9_-]+))? -->"),
)

REPORT_LIFECYCLE = ApprovalLifecycle(
    "bundle",
    "bundle-",
    re.compile(r"<!-- report-approvals: ([a-z0-9,-]*) -->"),
    "<!-- report-approvals: {ids} -->",
    allow_file_commands=False,
    finding_ids_include_prefix=True,
)


class ExampleSourceCheck(PullRequestSourceCheck[Finding]):
    """Exercise the source-check template without domain-specific scanning."""

    gate = "example"
    report_marker = "suppression"
    approval_lifecycle = LIFECYCLE

    def __init__(self) -> None:
        """Initialize observable rerun state."""
        self.rerun_numbers: list[int] = []

    @override
    def collect(self, context: CheckContext) -> CheckResult[Finding]:
        """Return a successful empty result for the pure collection contract."""
        return CheckResult((), Verdict.PASS)

    @override
    def collect_pull_request(
        self, github: RepositoryGitHubAPI, pull: dict[str, JsonValue]
    ) -> list[Finding]:
        """Return one deterministic source finding."""
        return [Finding("example.py", "one")]

    @override
    def render_summary(
        self, findings: list[Finding], approved: set[str], pull_request_url: str
    ) -> str:
        """Render an observable test report."""
        return f"active={len(findings) - len(approved)} url={pull_request_url}"

    @override
    def error_annotation(self, finding: Finding) -> str:
        """Render a deterministic workflow annotation."""
        return f"::error file={finding.path}::example"

    @override
    def rerun(self, github: RepositoryGitHubAPI, number: int) -> None:
        """Record requested reruns."""
        self.rerun_numbers.append(number)


def test_all_approval_gates_use_the_quality_check_contract() -> None:
    """Require every approvable gate to use the shared QualityCheck lifecycle."""
    checks = registered_checks()

    assert set(checks) == {"bundle", "frontend", "object", "suppression"}
    assert all(issubclass(check, QualityCheck) for check in checks.values())
    assert {gate for gate, check in checks.items() if check.supports_ignore_file} == {
        "object",
        "suppression",
    }
    assert {gate for gate, check in checks.items() if check.pending_marker is not None} == {
        "bundle",
        "frontend",
    }


def test_check_metadata_rejects_a_command_surface_report_marker() -> None:
    """Fail while defining a check whose report marker is not a check report."""
    with pytest.raises(TypeError, match="Unknown check report marker"):

        class InvalidCheck(QualityCheck[Finding]):
            gate = "example"
            report_marker = "quality-graph"
            approval_lifecycle = LIFECYCLE

            @override
            def collect(self, context: CheckContext) -> CheckResult[Finding]:
                findings = tuple(Finding(path, path) for path in context.files)
                return CheckResult(findings, Verdict.PASS)


def test_source_check_template_runs_the_shared_reporting_lifecycle() -> None:
    """Run collection, approval sync, reporting, and annotations in one template."""

    class PullGitHub(FakeGitHub):
        @override
        def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
            if method == "GET" and path == "/pulls/7":
                return {
                    "body": "<!-- example-approvals:  -->",
                    "html_url": "https://github.com/org/repo/pull/7",
                }
            return super().request(method, path, payload)

    github = PullGitHub()
    check = ExampleSourceCheck()
    report = mock.create_autospec(PullRequestReport, instance=True)
    error_output = io.StringIO()

    with (
        mock.patch.object(check, "report", return_value=report),
        contextlib.redirect_stderr(error_output),
    ):
        exit_code = check.run_pull_request_gate(github, {"pull_request": {"number": 7}})

    assert exit_code == 1
    report.mark_in_progress.assert_called_once_with()
    report.publish.assert_called_once_with("active=1 url=https://github.com/org/repo/pull/7")
    assert "::error file=example.py::example" in error_output.getvalue()
    assert check.rerun_numbers == []


def test_lifecycle_applies_admin_commands_and_persists_state() -> None:
    """Apply a gate-wide command through the reusable lifecycle."""
    github = FakeGitHub()
    command = parse_command("/qg ignore example")
    assert command is not None
    request = ApprovalRequest(github, 7, "", command, "admin", [])

    result = LIFECYCLE.sync(request, [Finding("example.py", "one")])

    assert result.approved == {"one"}
    assert result.authorized
    assert result.changed
    assert (
        "PATCH",
        "/pulls/7",
        {"body": "<!-- example-approvals: one -->"},
    ) in github.calls


def test_lifecycle_rejects_state_changes_from_non_admins() -> None:
    """Leave approvals unchanged when a non-admin submits a command."""
    github = FakeGitHub("write")
    command = parse_command("/qg ignore example-one")
    assert command is not None
    body = "<!-- example-approvals:  -->"

    result = LIFECYCLE.sync(
        ApprovalRequest(github, 7, body, command, "contributor", []),
        [Finding("example.py", "one")],
    )

    assert result.approved == set()
    assert not result.authorized
    assert not any(method == "PATCH" for method, _, _ in github.calls)


def test_declarative_report_lifecycle_filters_ids_and_disables_file_commands() -> None:
    """Honor report-check capabilities without gate-specific command code."""
    findings = [Finding("web/dist/app.js", "bundle-size")]
    mixed_command = parse_command("/qg ignore bundle-size,object-other")
    file_command = parse_command("/qg ignore-file web/dist/app.js")
    assert mixed_command is not None
    assert file_command is not None

    assert REPORT_LIFECYCLE.select_findings(mixed_command, findings) == {"bundle-size"}
    assert REPORT_LIFECYCLE.select_findings(file_command, findings) == set()


def test_pending_command_rejects_forged_encoded_marker() -> None:
    """Reject an encoded PR-body command without bot-owned authorization."""
    command = parse_command("/qg ignore bundle")
    assert command is not None
    encoded = encode_command(command)
    github = FakeGitHub(
        comments={
            1: {
                "body": f"<!-- monori-qg-authorized: bundle {encoded} -->",
                "user": {"login": "fork-author"},
            }
        }
    )

    resolved = PENDING_LIFECYCLE.pending_command(github, f"<!-- bundle-pending: 1 {encoded} -->")

    assert resolved is None


def test_pending_command_accepts_bot_owned_one_time_authorization() -> None:
    """Accept an encoded command only when a managed bot comment authorizes it."""
    command = parse_command("/qg ignore bundle")
    assert command is not None
    encoded = encode_command(command)
    github = FakeGitHub(
        comments={
            7: {
                "body": f"report\n<!-- monori-qg-authorized: bundle {encoded} -->",
                "user": {"login": "github-actions[bot]"},
            }
        }
    )

    resolved = PENDING_LIFECYCLE.pending_command(github, f"<!-- bundle-pending: 7 {encoded} -->")

    assert resolved == command

    PENDING_LIFECYCLE.consume_pending(github, f"<!-- bundle-pending: 7 {encoded} -->")

    assert github.calls[-1] == (
        "PATCH",
        "/issues/comments/7",
        {"body": "report"},
    )


def test_pending_sync_applies_and_consumes_bot_authorization() -> None:
    """Apply a pending command once and remove both authorization markers."""
    command = parse_command("/qg ignore bundle")
    assert command is not None
    encoded = encode_command(command)
    github = FakeGitHub(
        comments={
            7: {
                "body": f"report\n<!-- monori-qg-authorized: bundle {encoded} -->",
                "user": {"login": "github-actions[bot]"},
            }
        }
    )
    body = f"description\n<!-- bundle-pending: 7 {encoded} -->"

    result = PENDING_LIFECYCLE.sync_pending(github, 9, body, [Finding("report.json", "one")])

    assert result.approved == {"one"}
    assert result.authorized
    assert result.changed
    assert (
        "PATCH",
        "/pulls/9",
        {"body": "description\n\n<!-- bundle-approvals: one -->"},
    ) in github.calls
    assert (
        "PATCH",
        "/issues/comments/7",
        {"body": "report"},
    ) in github.calls


def test_pending_command_rejects_missing_source_comment() -> None:
    """Ignore a forged marker that references no GitHub comment."""
    command = parse_command("/qg ignore bundle")
    assert command is not None
    encoded = encode_command(command)

    resolved = PENDING_LIFECYCLE.pending_command(
        FakeGitHub(), f"<!-- bundle-pending: 404 {encoded} -->"
    )

    assert resolved is None
