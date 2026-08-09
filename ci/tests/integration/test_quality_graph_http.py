"""Exercise Quality Graph orchestration through the real GitHub HTTP client."""

from __future__ import annotations

import json
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, ClassVar, cast, override

import httpx
import pytest

from monori.ci.lib.annotations import SourceAnnotation
from monori.ci.lib.comments import comment_body, upsert_comment
from monori.ci.lib.github import GitHub, GitHubAPIError, rerun_latest_pull_request_workflow
from monori.ci.quality_graph.base import ApprovalLifecycle, PullRequestSourceCheck
from monori.ci.quality_graph.checks.bundle_size import BundleFinding, BundleSizeCheck
from monori.ci.quality_graph.checks.bundle_size import main as bundle_size_main
from monori.ci.quality_graph.checks.frontend_performance import (
    main as frontend_performance_main,
)
from monori.ci.quality_graph.checks.object_annotations import main as object_annotations_main
from monori.ci.quality_graph.checks.suppressions import APPROVALS as SUPPRESSION_APPROVALS
from monori.ci.quality_graph.checks.suppressions import main as suppressions_main
from monori.ci.quality_graph.commands import (
    CommandRequest,
    command_request,
    encode_command,
    parse_command,
    process_command,
)
from monori.ci.quality_graph.dashboard import (
    DashboardLifecycle,
    mark_jobs_pending,
    update_dashboard_notice,
)
from monori.ci.quality_graph.job_results import (
    JobControl,
    JobResult,
    JobResultPublisher,
    JobStatus,
    read_job_result,
    write_job_result,
)
from monori.ci.quality_graph.models import CheckContext, CheckResult, Verdict
from monori.ci.quality_graph.registry import workflow_jobs
from monori.ci.quality_graph.reporting import main as reporting_main
from monori.common import JsonValue, array_value, object_value, string_value

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from monori.ci.lib.github import RepositoryGitHubAPI

FAKE_GITHUB_URL = os.environ.get("GITHUB_API_URL", "http://fake-github.invalid")
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "alchemmist/monori")
PULL_REQUEST_NUMBER = 7
FAILURE_LABEL = "monori-scenario-failed"
BUNDLE_REPORT_COMMENT_ID = 20
COMMAND_COMMENT_ID = 21
SERVICE_UNAVAILABLE = 503
pytestmark = pytest.mark.integration
SCENARIO_APPROVALS = ApprovalLifecycle(
    "object",
    "object-",
    re.compile(r"<!-- scenario-approvals: ([a-z0-9,-]*) -->"),
    "<!-- scenario-approvals: {ids} -->",
)


@dataclass(frozen=True)
class ScenarioFinding:
    """Represent one deterministic integration-test finding."""

    finding_id: str
    path: str


class ScenarioCheck(PullRequestSourceCheck[ScenarioFinding]):
    """Drive the shared source-check lifecycle with configured findings."""

    gate = "object"
    job_id = "object-annotations"
    report_marker = "object-annotations"
    approval_lifecycle = SCENARIO_APPROVALS
    failure_label: ClassVar[str | None] = FAILURE_LABEL

    def __init__(self, findings: list[ScenarioFinding]) -> None:
        """Initialize the check with deterministic domain findings."""
        self.findings = findings

    @override
    def collect(self, context: CheckContext) -> CheckResult[ScenarioFinding]:
        """Return configured findings through the pure check contract."""
        if context.files:
            message = "Scenario checks do not accept source files"
            raise ValueError(message)
        verdict = Verdict.FAIL if self.findings else Verdict.PASS
        return CheckResult(tuple(self.findings), verdict)

    @override
    def collect_pull_request(
        self, github: RepositoryGitHubAPI, pull: dict[str, JsonValue]
    ) -> list[ScenarioFinding]:
        """Return configured findings after confirming pull-request state is readable."""
        object_value(
            github.request("GET", f"/pulls/{pull['number']}"),
            "scenario pull request",
        )
        return self.findings

    @override
    def render_summary(
        self,
        findings: list[ScenarioFinding],
        approved: set[str],
        pull_request_url: str,
    ) -> str:
        """Render enough domain state to verify report replacement semantics."""
        return (
            f"Scenario report for {pull_request_url}: "
            f"{len(findings)} findings, {len(approved)} approved."
        )

    @override
    def source_annotation(self, finding: ScenarioFinding) -> SourceAnnotation:
        """Build one source annotation for an active scenario finding."""
        return SourceAnnotation(finding.path, 1, 1, finding.finding_id)


def reset_fake_github(overrides: dict[str, JsonValue] | None = None) -> None:
    """Reset the service to one complete pull-request scenario."""
    state: dict[str, JsonValue] = {
        "pulls": cast(
            "JsonValue",
            [
                {
                    "number": PULL_REQUEST_NUMBER,
                    "body": "Pull request body",
                    "html_url": f"https://github.com/{REPOSITORY}/pull/{PULL_REQUEST_NUMBER}",
                    "head": {"sha": "head-sha"},
                    "base": {"sha": "base-sha"},
                }
            ],
        ),
        "comments": [],
        "permissions": {"admin": "admin", "contributor": "write"},
        "workflow_runs": cast(
            "JsonValue",
            [
                {
                    "id": 99,
                    "created_at": "2026-08-06T00:00:00Z",
                    "head_sha": "head-sha",
                    "run_attempt": 1,
                    "html_url": "https://example.test/runs/99",
                    "pull_requests": [{"number": PULL_REQUEST_NUMBER}],
                }
            ],
        ),
        "pull_files": {str(PULL_REQUEST_NUMBER): []},
        "comparisons": {"base-sha...head-sha": {"merge_base_commit": {"sha": "base-sha"}}},
    }
    state.update(overrides or {})
    response = httpx.post(f"{FAKE_GITHUB_URL}/_test/reset", json=state)
    response.raise_for_status()


def fake_state() -> dict[str, JsonValue]:
    """Read the fake service state after an orchestration scenario."""
    response = httpx.get(f"{FAKE_GITHUB_URL}/_test/state")
    response.raise_for_status()
    return object_value(cast("JsonValue", response.json()), "fake GitHub state")


def state_objects(state: dict[str, JsonValue], key: str) -> list[dict[str, JsonValue]]:
    """Read an object list from one fake service state field."""
    return [object_value(item, key) for item in array_value(state.get(key), key)]


def pull_request_event() -> dict[str, JsonValue]:
    """Build the pull-request event consumed by source checks."""
    return {"pull_request": {"number": PULL_REQUEST_NUMBER}}


def checkbox_event(
    comment_id: int, body: str, previous_body: str, sender: str = "admin"
) -> dict[str, JsonValue]:
    """Build a bot-comment edit event caused by one checkbox change."""
    return {
        "action": "edited",
        "comment": {
            "id": comment_id,
            "body": body,
            "user": {"login": "github-actions[bot]"},
        },
        "changes": {"body": {"from": previous_body}},
        "issue": {"number": PULL_REQUEST_NUMBER, "pull_request": {"url": "fake"}},
        "sender": {"login": sender},
    }


def checkbox_body(body: str, *, checked: bool) -> str:
    """Set the first administrator control to the requested checkbox state."""
    source = "- [ ]" if checked else "- [x]"
    target = "- [x]" if checked else "- [ ]"
    return body.replace(source, target, 1)


def result_control_body(path: Path) -> str:
    """Render the first portable result control as dashboard Markdown."""
    control = read_job_result(path).controls[0]
    state = "x" if control.checked else " "
    return f"- [{state}] `{control.command}` <!-- {control.marker} -->\n"


@contextmanager
def environment(values: dict[str, str]) -> Iterator[None]:
    """Temporarily set process environment values for a CLI scenario."""
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def arguments(values: list[str]) -> Iterator[None]:
    """Temporarily replace command-line arguments for a CLI scenario."""
    previous = sys.argv
    sys.argv = values
    try:
        yield
    finally:
        sys.argv = previous


def test_source_gate_converges_labels_and_writes_job_results(tmp_path: Path) -> None:
    """Publish red and green results without creating gate-specific comments."""
    reset_fake_github()
    github = GitHub()
    result_path = tmp_path / "result.json"
    summary_path = tmp_path / "summary.md"

    publisher = JobResultPublisher(result_path, summary_path)
    failed = ScenarioCheck([ScenarioFinding("finding-1", "example.py")])
    assert failed.run_pull_request_gate(github, pull_request_event(), publisher) == 1
    failed_result = result_path.read_text()
    assert '"status": "failed"' in failed_result
    passed = ScenarioCheck([])
    assert passed.run_pull_request_gate(github, pull_request_event(), publisher) == 0
    final_state = fake_state()
    assert final_state["issue_labels"] == {str(PULL_REQUEST_NUMBER): []}
    assert state_objects(final_state, "comments") == []
    assert '"status": "passed"' in result_path.read_text()
    assert "0 findings" in summary_path.read_text()


def test_source_gate_read_only_mode_avoids_pull_request_mutations(tmp_path: Path) -> None:
    """Evaluate fork findings without requiring labels or pull-request write access."""
    reset_fake_github(
        {
            "failures": [
                {
                    "method": "PATCH",
                    "path": f"/repos/{REPOSITORY}/pulls/{PULL_REQUEST_NUMBER}",
                    "status": HTTPStatus.FORBIDDEN,
                },
                {
                    "method": "POST",
                    "path": f"/repos/{REPOSITORY}/issues/{PULL_REQUEST_NUMBER}/labels",
                    "status": HTTPStatus.FORBIDDEN,
                },
            ]
        }
    )
    result_path = tmp_path / "result.json"

    exit_code = ScenarioCheck([ScenarioFinding("finding-1", "example.py")]).run_pull_request_gate(
        GitHub(),
        pull_request_event(),
        JobResultPublisher(result_path),
        read_only=True,
    )

    assert exit_code == 1
    assert read_job_result(result_path).status is JobStatus.FAILED


def test_dashboard_replaces_legacy_comments_and_collects_job_results(tmp_path: Path) -> None:
    """Publish one comment from isolated job artifacts and real Actions API state."""
    reset_fake_github(
        {
            "comments": [
                {
                    "id": 30,
                    "issue_number": PULL_REQUEST_NUMBER,
                    "body": "<!-- monori-report: suppression -->\n\nOld report",
                    "user": {"login": "github-actions[bot]"},
                    "reactions": [],
                }
            ],
            "workflow_jobs": {
                "99": [
                    {
                        "name": "Lint",
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "https://example.test/jobs/lint",
                    }
                ]
            },
        }
    )
    lifecycle = DashboardLifecycle(
        GitHub(),
        PULL_REQUEST_NUMBER,
        99,
        1,
        "head-sha",
        "https://example.test/runs/99",
    )

    lifecycle.start()
    write_job_result(
        tmp_path / "lint.json",
        JobResult("lint", "Lint", JobStatus.FAILED, "Detailed lint output"),
    )
    lifecycle.finish(tmp_path)

    comments = state_objects(fake_state(), "comments")
    assert len(comments) == 1
    body = string_value(comments[0].get("body"), "dashboard body")
    assert "monori-report: quality-graph" in body
    assert "| Lint | ❌ failed |" in body
    assert "example.test/jobs/lint" in body
    assert "monori-report: suppression" not in body


def test_dashboard_uses_saved_result_when_partial_rerun_omits_a_job(tmp_path: Path) -> None:
    """Keep a prior successful job passed when the latest attempt does not rerun it."""
    reset_fake_github(
        {
            "workflow_jobs": {
                "99": [
                    {
                        "id": 20,
                        "name": "Frontend bundle size",
                        "run_attempt": 2,
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://example.test/jobs/bundle-size",
                    }
                ]
            }
        }
    )
    lifecycle = DashboardLifecycle(
        GitHub(),
        PULL_REQUEST_NUMBER,
        99,
        2,
        "head-sha",
        "https://example.test/runs/99",
    )
    write_job_result(
        tmp_path / "quality-result-fmt-check-1" / "fmt-check.json",
        JobResult("fmt-check", "Format check", JobStatus.PASSED),
    )

    lifecycle.finish(tmp_path)

    body = string_value(state_objects(fake_state(), "comments")[0].get("body"), "dashboard body")
    assert "| Format check | ✅ passed |" in body


def test_dashboard_single_writer_preserves_concurrent_job_completions() -> None:
    """Publish one API snapshot containing two concurrently completed jobs."""
    reset_fake_github()
    lifecycle = DashboardLifecycle(
        GitHub(),
        PULL_REQUEST_NUMBER,
        99,
        1,
        "head-sha",
        "https://example.test/runs/99",
    )
    lifecycle.start()

    jobs: list[JsonValue] = [
        {
            "name": definition.title,
            "status": "completed",
            "conclusion": "failure" if definition.job_id == "suppressions" else "success",
            "html_url": f"https://example.test/jobs/{definition.job_id}",
        }
        for definition in workflow_jobs().values()
    ]
    state = fake_state()
    state["workflow_jobs"] = {"99": jobs}
    reset_fake_github(state)

    lifecycle.watch(0, 1)

    body = string_value(state_objects(fake_state(), "comments")[0].get("body"), "dashboard")
    assert "| Workflow graph validation | ✅ passed |" in body
    assert "| Format check | ✅ passed |" in body
    assert "[Logs](https://example.test/jobs/workflow-graph)" in body
    assert "[Logs](https://example.test/jobs/suppressions)" in body
    assert "| Lint suppression gate | ❌ failed |" in body


def test_stale_dashboard_run_cannot_overwrite_the_current_comment(tmp_path: Path) -> None:
    """Ignore a final renderer whose head SHA no longer belongs to the pull request."""
    reset_fake_github()
    current = DashboardLifecycle(
        GitHub(),
        PULL_REQUEST_NUMBER,
        99,
        1,
        "head-sha",
        "https://example.test/runs/99",
    )
    current.start()
    before = string_value(state_objects(fake_state(), "comments")[0].get("body"), "dashboard body")

    stale = DashboardLifecycle(
        GitHub(),
        PULL_REQUEST_NUMBER,
        98,
        1,
        "old-sha",
        "https://example.test/runs/98",
    )
    stale.finish(tmp_path)

    after = string_value(state_objects(fake_state(), "comments")[0].get("body"), "dashboard body")
    assert after == before


def test_new_run_resets_stale_dashboard_while_runs_api_is_delayed() -> None:
    """Publish pending state when GitHub has not indexed the newly started run yet."""
    reset_fake_github(
        {
            "workflow_runs": [
                {
                    "id": 98,
                    "created_at": "2026-08-06T00:00:00Z",
                    "head_sha": "previous-sha",
                    "run_attempt": 1,
                    "html_url": "https://example.test/runs/98",
                    "pull_requests": [{"number": PULL_REQUEST_NUMBER}],
                }
            ]
        }
    )
    github = GitHub()
    upsert_comment(
        github,
        PULL_REQUEST_NUMBER,
        "quality-graph",
        "## ❌ Quality Graph\n\n| Check | Status |\n| --- | --- |\n| Format check | ❌ failed |",
    )

    DashboardLifecycle(
        github,
        PULL_REQUEST_NUMBER,
        99,
        1,
        "head-sha",
        "https://example.test/runs/99",
    ).start()

    body = string_value(state_objects(fake_state(), "comments")[0].get("body"), "dashboard")
    assert "## 🚀 Quality Graph" in body
    assert "| Workflow graph validation | 🚀 in progress |" in body
    assert "| Format check | ⏳ wait |" in body
    assert body.count("[Logs](https://example.test/runs/99)") == len(workflow_jobs())
    assert "❌" not in body


def test_stale_run_attempt_cannot_replace_the_current_dashboard() -> None:
    """Reject an older rerun attempt even when GitHub reuses its workflow run ID."""
    reset_fake_github(
        {
            "workflow_runs": [
                {
                    "id": 99,
                    "created_at": "2026-08-06T00:00:00Z",
                    "head_sha": "head-sha",
                    "run_attempt": 2,
                    "html_url": "https://example.test/runs/99",
                    "pull_requests": [{"number": PULL_REQUEST_NUMBER}],
                }
            ]
        }
    )

    DashboardLifecycle(
        GitHub(),
        PULL_REQUEST_NUMBER,
        99,
        1,
        "head-sha",
        "https://example.test/runs/99",
    ).start()

    assert state_objects(fake_state(), "comments") == []


def test_dashboard_aggregation_failure_replaces_pending_status() -> None:
    """Avoid leaving an indefinitely pending dashboard after renderer failure."""
    reset_fake_github()
    lifecycle = DashboardLifecycle(
        GitHub(),
        PULL_REQUEST_NUMBER,
        99,
        1,
        "head-sha",
        "https://example.test/runs/99",
    )
    lifecycle.start()

    lifecycle.fail("Could not load workflow jobs.")

    body = string_value(state_objects(fake_state(), "comments")[0].get("body"), "dashboard body")
    assert "## ❌ Quality Graph" in body
    assert "Could not load workflow jobs." in body


def test_command_status_updates_notice_without_replacing_dashboard() -> None:
    """Keep the status table and controls when command feedback is published."""
    command_comment: dict[str, JsonValue] = {
        "id": COMMAND_COMMENT_ID,
        "issue_number": PULL_REQUEST_NUMBER,
        "body": "/qg status",
        "user": {"login": "admin"},
        "reactions": [],
    }
    reset_fake_github({"comments": cast("JsonValue", [command_comment])})
    DashboardLifecycle(
        GitHub(),
        PULL_REQUEST_NUMBER,
        99,
        1,
        "head-sha",
        "https://example.test/runs/99",
    ).start()

    process_command(
        GitHub(),
        CommandRequest(COMMAND_COMMENT_ID, "/qg status", "admin", PULL_REQUEST_NUMBER),
    )

    dashboard = next(
        comment
        for comment in state_objects(fake_state(), "comments")
        if "monori-report: quality-graph" in str(comment.get("body"))
    )
    body = string_value(dashboard.get("body"), "dashboard body")
    assert "| Workflow graph validation |" in body
    assert "Command API is available" in body


def test_dashboard_pending_update_ignores_unknown_jobs_and_preserves_backslashes() -> None:
    """Update valid rows and notices even when a caller supplies stale job metadata."""
    reset_fake_github()
    github = GitHub()
    DashboardLifecycle(
        github,
        PULL_REQUEST_NUMBER,
        99,
        1,
        "head-sha",
        "https://example.test/runs/99",
    ).start()

    mark_jobs_pending(github, PULL_REQUEST_NUMBER, {"fmt-check", "removed-job"})
    update_dashboard_notice(github, PULL_REQUEST_NUMBER, r"Command contains \1 literally")

    body = string_value(state_objects(fake_state(), "comments")[0].get("body"), "dashboard")
    assert "| Format check | 🚀 in progress |" in body
    assert r"Command contains \1 literally" in body


def test_pending_admin_command_is_reacted_to_consumed_and_rerun() -> None:
    """Apply an administrator command through reactions and pending approval state."""
    bundle_report: dict[str, JsonValue] = {
        "id": BUNDLE_REPORT_COMMENT_ID,
        "issue_number": PULL_REQUEST_NUMBER,
        "body": "<!-- monori-report: quality-graph -->\n\nBundle report\n",
        "user": {"login": "github-actions[bot]"},
        "reactions": [],
    }
    command_comment: dict[str, JsonValue] = {
        "id": COMMAND_COMMENT_ID,
        "issue_number": PULL_REQUEST_NUMBER,
        "body": "/qg ignore bundle",
        "user": {"login": "admin"},
        "reactions": [
            {
                "id": 1,
                "content": "eyes",
                "user": {"login": "github-actions[bot]"},
            }
        ],
    }
    reset_fake_github({"comments": cast("JsonValue", [bundle_report, command_comment])})

    process_command(
        GitHub(),
        CommandRequest(
            COMMAND_COMMENT_ID,
            "/qg ignore bundle",
            "admin",
            PULL_REQUEST_NUMBER,
        ),
    )
    armed = fake_state()
    pull = state_objects(armed, "pulls")[0]
    comments = state_objects(armed, "comments")
    report = next(comment for comment in comments if comment.get("id") == BUNDLE_REPORT_COMMENT_ID)
    command = next(comment for comment in comments if comment.get("id") == COMMAND_COMMENT_ID)
    authorization = next(
        comment
        for comment in comments
        if "monori-qg-authorized: bundle" in string_value(comment.get("body"), "comment body")
    )
    pull_body = string_value(pull.get("body"), "pull request body")
    report_body = string_value(report.get("body"), "report body")
    reactions = state_objects(command, "reactions")
    assert "monori-bundle-size-pending" in pull_body
    assert "monori-qg-authorized" not in report_body
    assert [reaction.get("content") for reaction in reactions] == ["hooray"]
    assert armed["rerun_requests"] == [99]

    GitHub().request(
        "PATCH",
        f"/issues/comments/{BUNDLE_REPORT_COMMENT_ID}",
        {"body": "<!-- monori-report: quality-graph -->\n\nWatcher refresh\n"},
    )

    sync = BundleSizeCheck().sync_pending_approvals(
        GitHub(),
        PULL_REQUEST_NUMBER,
        pull_body,
        [BundleFinding("bundle-initial-load")],
    )
    consumed = fake_state()
    consumed_pull = state_objects(consumed, "pulls")[0]
    consumed_pull_body = string_value(consumed_pull.get("body"), "pull request body")
    assert sync.approved == {"bundle-initial-load"}
    assert "monori-bundle-size-pending" not in consumed_pull_body
    assert "monori-bundle-size-approvals: bundle-initial-load" in consumed_pull_body
    assert all(
        comment.get("id") != authorization.get("id")
        for comment in state_objects(consumed, "comments")
    )


def test_checkbox_applies_and_reverses_bundle_approval(tmp_path: Path) -> None:
    """Drive a reversible report checkbox through command dispatch and the bundle gate."""
    report_data = {
        "prNumber": PULL_REQUEST_NUMBER,
        "verdict": "critical",
        "entries": [
            {
                "id": "bundle-initial-load",
                "label": "Initial load",
                "base": 1000,
                "current": 2000,
                "delta": 1000,
                "percent": 100.0,
                "tier": "critical",
            }
        ],
        "assetGrowth": [],
    }
    report_path = tmp_path / "bundle.json"
    summary_path = tmp_path / "bundle.md"
    result_path = tmp_path / "bundle-result.json"
    report_path.write_text(json.dumps(report_data))
    with environment(
        {
            "REPORT_PATH": str(report_path),
            "SUMMARY_PATH": str(summary_path),
            "QUALITY_RESULT_PATH": str(result_path),
        }
    ):
        reset_fake_github()
        assert bundle_size_main() == 1
        upsert_comment(
            GitHub(), PULL_REQUEST_NUMBER, "quality-graph", result_control_body(result_path)
        )
        state = fake_state()
        report = next(
            comment
            for comment in state_objects(state, "comments")
            if "monori-report: quality-graph" in str(comment.get("body"))
        )
        unchecked = string_value(report.get("body"), "bundle report")
        checked = checkbox_body(unchecked, checked=True)
        GitHub().request(
            "PATCH",
            f"/issues/comments/{report['id']}",
            {"body": checked},
        )
        report_id = report.get("id")
        assert isinstance(report_id, int)
        request = command_request(checkbox_event(report_id, checked, unchecked))
        assert request is not None
        process_command(GitHub(), request)

        armed = fake_state()
        armed_report = next(
            comment
            for comment in state_objects(armed, "comments")
            if comment.get("id") == report.get("id")
        )
        assert [
            reaction.get("content") for reaction in state_objects(armed_report, "reactions")
        ] == ["hooray"]
        assert armed["rerun_requests"] == [99]

        report_path.write_text(json.dumps(report_data))
        assert bundle_size_main() == 0
        upsert_comment(
            GitHub(), PULL_REQUEST_NUMBER, "quality-graph", result_control_body(result_path)
        )
        approved = fake_state()
        pull = state_objects(approved, "pulls")[0]
        assert "monori-bundle-size-approvals: bundle-initial-load" in string_value(
            pull.get("body"), "pull request body"
        )
        approved_report = next(
            comment
            for comment in state_objects(approved, "comments")
            if comment.get("id") == report.get("id")
        )
        checked = string_value(approved_report.get("body"), "approved report")
        unchecked = checkbox_body(checked, checked=False)
        GitHub().request(
            "PATCH",
            f"/issues/comments/{report['id']}",
            {"body": unchecked},
        )
        request = command_request(checkbox_event(report_id, unchecked, checked))
        assert request is not None
        process_command(GitHub(), request)

        report_path.write_text(json.dumps(report_data))
        assert bundle_size_main() == 1
        reverted = fake_state()
        pull = state_objects(reverted, "pulls")[0]
        assert "monori-bundle-size-approvals:  -->" in string_value(
            pull.get("body"), "pull request body"
        )
        assert reverted["rerun_requests"] == [99, 99]


def test_ignore_file_approves_only_findings_from_selected_file(tmp_path: Path) -> None:
    """Apply an ignore-file command through a concrete source gate over HTTP."""
    reset_fake_github(
        {
            "pull_files": {
                str(PULL_REQUEST_NUMBER): [
                    {
                        "filename": "first.py",
                        "status": "modified",
                        "patch": "@@ -0,0 +1 @@\n+value = 1  # noqa",
                    },
                    {
                        "filename": "second.py",
                        "status": "modified",
                        "patch": "@@ -0,0 +1 @@\n+value = 2  # noqa",
                    },
                ]
            },
            "contents": {
                "head-sha:first.py": "value = 1  # noqa\n",
                "head-sha:second.py": "value = 2  # noqa\n",
                "base-sha:first.py": "",
                "base-sha:second.py": "",
            },
        }
    )
    event_path = tmp_path / "event.json"
    result_path = tmp_path / "result.json"
    summary_path = tmp_path / "summary.md"
    event_path.write_text(
        json.dumps(
            {
                "action": "created",
                "comment": {
                    "body": "/qg ignore-file first.py",
                    "id": COMMAND_COMMENT_ID,
                    "user": {"login": "admin"},
                },
                "issue": {"number": PULL_REQUEST_NUMBER, "pull_request": {"url": "fake"}},
                "sender": {"login": "admin"},
            }
        )
    )
    with environment(
        {
            "GITHUB_EVENT_PATH": str(event_path),
            "QUALITY_RESULT_PATH": str(result_path),
            "GITHUB_STEP_SUMMARY": str(summary_path),
        }
    ):
        assert suppressions_main() == 1

    state = fake_state()
    pull = state_objects(state, "pulls")[0]
    body = string_value(pull.get("body"), "pull request body")
    approvals = SUPPRESSION_APPROVALS.read(body)
    report_body = summary_path.read_text()
    assert len(approvals) == 1
    assert "first.py" in report_body
    assert "second.py" in report_body
    assert report_body.count("- ✔") == 1
    assert report_body.count("- ✗") == 1


def test_forged_pending_marker_is_not_applied() -> None:
    """Reject a pending command that lacks bot-owned report authorization."""
    command = parse_command("/qg ignore bundle")
    assert command is not None
    encoded = encode_command(command)
    report: dict[str, JsonValue] = {
        "id": BUNDLE_REPORT_COMMENT_ID,
        "issue_number": PULL_REQUEST_NUMBER,
        "body": "<!-- monori-report: quality-graph -->\n\nBundle report\n",
        "user": {"login": "github-actions[bot]"},
        "reactions": [],
    }
    pull_body = f"<!-- monori-bundle-size-pending: {BUNDLE_REPORT_COMMENT_ID} {encoded} -->"
    reset_fake_github(
        {
            "pulls": [
                {
                    "number": PULL_REQUEST_NUMBER,
                    "body": pull_body,
                    "html_url": f"https://github.com/{REPOSITORY}/pull/{PULL_REQUEST_NUMBER}",
                    "head": {"sha": "head-sha"},
                    "base": {"sha": "base-sha"},
                }
            ],
            "comments": [report],
        }
    )

    sync = BundleSizeCheck().sync_pending_approvals(
        GitHub(),
        PULL_REQUEST_NUMBER,
        pull_body,
        [BundleFinding("bundle-initial-load")],
    )

    assert sync.approved == set()
    assert not sync.authorized
    pull = state_objects(fake_state(), "pulls")[0]
    assert "monori-bundle-size-pending" in string_value(pull.get("body"), "pull body")


def test_non_admin_command_is_rejected_with_a_final_reaction() -> None:
    """Reject a contributor command without changing approval state."""
    command_comment: dict[str, JsonValue] = {
        "id": COMMAND_COMMENT_ID,
        "issue_number": PULL_REQUEST_NUMBER,
        "body": "/qg status",
        "user": {"login": "contributor"},
        "reactions": [],
    }
    reset_fake_github({"comments": cast("JsonValue", [command_comment])})

    process_command(
        GitHub(),
        CommandRequest(
            COMMAND_COMMENT_ID,
            "/qg status",
            "contributor",
            PULL_REQUEST_NUMBER,
        ),
    )

    state = fake_state()
    command = next(
        comment
        for comment in state_objects(state, "comments")
        if comment.get("id") == COMMAND_COMMENT_ID
    )
    reactions = state_objects(command, "reactions")
    assert [reaction.get("content") for reaction in reactions] == ["confused"]
    assert state["rerun_requests"] == []


def test_invalid_command_and_missing_report_fail_visibly() -> None:
    """Publish command validation and dispatch failures through final reactions."""
    comment = {
        "id": COMMAND_COMMENT_ID,
        "issue_number": PULL_REQUEST_NUMBER,
        "body": "/qg ignore unknown-target",
        "user": {"login": "admin"},
        "reactions": [],
    }
    reset_fake_github({"comments": cast("JsonValue", [comment])})
    process_command(
        GitHub(),
        CommandRequest(
            COMMAND_COMMENT_ID,
            "/qg ignore unknown-target",
            "admin",
            PULL_REQUEST_NUMBER,
        ),
    )
    state = fake_state()
    rejected = next(
        item for item in state_objects(state, "comments") if item.get("id") == COMMAND_COMMENT_ID
    )
    assert [reaction.get("content") for reaction in state_objects(rejected, "reactions")] == ["x"]

    comment["body"] = "/qg ignore bundle"
    comment["reactions"] = []
    reset_fake_github({"comments": cast("JsonValue", [comment])})
    with pytest.raises(RuntimeError, match="without a Quality Graph dashboard"):
        process_command(
            GitHub(),
            CommandRequest(
                COMMAND_COMMENT_ID,
                "/qg ignore bundle",
                "admin",
                PULL_REQUEST_NUMBER,
            ),
        )
    state = fake_state()
    failed = next(
        item for item in state_objects(state, "comments") if item.get("id") == COMMAND_COMMENT_ID
    )
    assert [reaction.get("content") for reaction in state_objects(failed, "reactions")] == ["x"]


@pytest.mark.parametrize("status_code", [403, SERVICE_UNAVAILABLE])
def test_client_surfaces_typed_server_errors(status_code: int) -> None:
    """Expose unexpected fake responses through the production error type."""
    path = f"/repos/{REPOSITORY}/pulls/{PULL_REQUEST_NUMBER}"
    reset_fake_github(
        {
            "failures": cast(
                "JsonValue",
                [{"method": "GET", "path": path, "status": status_code}],
            )
        }
    )

    with pytest.raises(GitHubAPIError) as error:
        GitHub().request("GET", f"/pulls/{PULL_REQUEST_NUMBER}")

    assert error.value.status_code == status_code


def test_bundle_and_performance_gates_publish_real_http_state(tmp_path: Path) -> None:
    """Apply report gates through files and the real HTTP client."""
    reset_fake_github()
    bundle_report = tmp_path / "bundle.json"
    bundle_summary = tmp_path / "bundle.md"
    bundle_report.write_text(
        json.dumps(
            {
                "prNumber": PULL_REQUEST_NUMBER,
                "verdict": "critical",
                "entries": [
                    {
                        "id": "bundle-initial-load",
                        "label": "Initial load",
                        "base": 1000,
                        "current": 2000,
                        "delta": 1000,
                        "percent": 100.0,
                        "tier": "critical",
                    }
                ],
                "assetGrowth": [],
            }
        )
    )
    with environment({"REPORT_PATH": str(bundle_report), "SUMMARY_PATH": str(bundle_summary)}):
        assert bundle_size_main() == 1
    assert "Initial load" in bundle_summary.read_text()

    performance_report = tmp_path / "performance.json"
    performance_summary = tmp_path / "performance.md"
    performance_report.write_text(
        json.dumps(
            {
                "prNumber": PULL_REQUEST_NUMBER,
                "verdict": "critical",
                "entries": [
                    {
                        "route_id": "dashboard",
                        "route_label": "Dashboard",
                        "metric_id": "lcp",
                        "metric_label": "LCP",
                        "tier": "critical",
                    }
                ],
            }
        )
    )
    performance_summary.write_text("## Previous heading\n\nMeasured details.\n")
    with environment(
        {"REPORT_PATH": str(performance_report), "SUMMARY_PATH": str(performance_summary)}
    ):
        assert frontend_performance_main() == 1
    assert "Dashboard · LCP" in performance_summary.read_text()
    state = fake_state()
    assert set(array_value(state["labels"], "labels")) == {
        "monori-bundle-size-failed",
        "monori-frontend-performance-failed",
    }


def test_reporting_cli_updates_one_comment_and_reaction(tmp_path: Path) -> None:
    """Exercise report and reaction CLI operations over the fake service."""
    command_comment: dict[str, JsonValue] = {
        "id": COMMAND_COMMENT_ID,
        "issue_number": PULL_REQUEST_NUMBER,
        "body": "/qg status",
        "user": {"login": "admin"},
        "reactions": [],
    }
    reset_fake_github({"comments": cast("JsonValue", [command_comment])})
    body = tmp_path / "body.md"
    body.write_text("Measured details.\n")

    with arguments(
        [
            "reporting",
            "in-progress",
            "--marker",
            "bundle-size",
            "--pr-number",
            str(PULL_REQUEST_NUMBER),
        ]
    ):
        assert reporting_main() == 0
    with arguments(
        [
            "reporting",
            "complete",
            "--marker",
            "bundle-size",
            "--pr-number",
            str(PULL_REQUEST_NUMBER),
            "--status",
            "passed",
            "--body-file",
            str(body),
        ]
    ):
        assert reporting_main() == 0
    with arguments(
        [
            "reporting",
            "react",
            "--comment-id",
            str(COMMAND_COMMENT_ID),
            "--reaction",
            "hooray",
        ]
    ):
        assert reporting_main() == 0

    state = fake_state()
    comments = state_objects(state, "comments")
    reports = [item for item in comments if "monori-report: bundle-size" in str(item.get("body"))]
    assert len(reports) == 1
    command = next(item for item in comments if item.get("id") == COMMAND_COMMENT_ID)
    reactions = state_objects(command, "reactions")
    assert [item.get("content") for item in reactions] == ["hooray"]


def test_repository_client_helpers_converge_real_http_state() -> None:
    """Exercise pagination, permissions, labels, missing data, and absent reruns."""
    reset_fake_github()
    github = GitHub()

    assert github.paged(f"/issues/{PULL_REQUEST_NUMBER}/comments") == []
    github.ensure_label("scenario-label")
    github.ensure_label("scenario-label")
    assert github.is_admin("admin")
    assert not github.is_admin("unknown")
    github.sync_label(PULL_REQUEST_NUMBER, "scenario-label", present=True)
    github.sync_label(PULL_REQUEST_NUMBER, "scenario-label", present=False)
    assert github.request("GET", "/pulls/999") is None
    assert github.file_text("missing.py", "head-sha") is None
    assert github.request("DELETE", f"/issues/{PULL_REQUEST_NUMBER}/labels/missing") is None

    permission_path = f"/repos/{REPOSITORY}/collaborators/blocked/permission"
    reset_fake_github(
        {
            "failures": cast(
                "JsonValue",
                [{"method": "GET", "path": permission_path, "status": 403}],
            )
        }
    )
    assert not github.is_admin("blocked")

    reset_fake_github({"workflow_runs": []})
    with pytest.raises(RuntimeError, match=re.escape("No pr-checks.yaml run found")):
        rerun_latest_pull_request_workflow(github, PULL_REQUEST_NUMBER)


def test_repository_client_reads_all_comment_and_file_pages() -> None:
    """Follow fake GitHub pagination with the production repository client."""
    comments = [
        {
            "id": identifier,
            "issue_number": PULL_REQUEST_NUMBER,
            "body": f"comment-{identifier}",
            "user": {"login": "contributor"},
            "reactions": [],
        }
        for identifier in range(1, 102)
    ]
    files = [
        {"filename": f"file-{identifier}.py", "status": "modified", "patch": ""}
        for identifier in range(1, 102)
    ]
    reset_fake_github(
        {
            "comments": cast("JsonValue", comments),
            "pull_files": {str(PULL_REQUEST_NUMBER): cast("JsonValue", files)},
        }
    )

    github = GitHub()

    assert len(github.paged(f"/issues/{PULL_REQUEST_NUMBER}/comments")) == 101
    assert len(github.paged(f"/pulls/{PULL_REQUEST_NUMBER}/files")) == 101


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("page", "invalid"),
        ("page", "0"),
        ("page", "-1"),
        ("per_page", "invalid"),
        ("per_page", "0"),
        ("per_page", "-1"),
    ],
)
def test_fake_github_rejects_invalid_pagination(parameter: str, value: str) -> None:
    """Return a client error for malformed or non-positive pagination values."""
    response = httpx.get(
        f"{FAKE_GITHUB_URL}/repos/{REPOSITORY}/issues/{PULL_REQUEST_NUMBER}/comments",
        params={parameter: value},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {"message": "invalid pagination parameters"}


def test_workflow_rerun_follows_pagination_and_replaces_reaction() -> None:
    """Find a matching workflow on page two and replace an acknowledgement reaction."""
    runs = [
        {
            "id": identifier,
            "created_at": f"2026-08-05T00:{identifier % 60:02d}:00Z",
            "head_sha": f"unrelated-{identifier}",
            "pull_requests": [],
        }
        for identifier in range(1, 101)
    ]
    runs.append(
        {
            "id": 999,
            "created_at": "2026-08-06T00:00:00Z",
            "head_sha": "head-sha",
            "pull_requests": [{"number": PULL_REQUEST_NUMBER}],
        }
    )
    command_comment = {
        "id": COMMAND_COMMENT_ID,
        "issue_number": PULL_REQUEST_NUMBER,
        "body": "/qg status",
        "user": {"login": "admin"},
        "reactions": [
            {
                "id": 1,
                "content": "eyes",
                "user": {"login": "github-actions[bot]"},
            }
        ],
    }
    reset_fake_github(
        {
            "workflow_runs": cast("JsonValue", runs),
            "comments": cast("JsonValue", [command_comment]),
        }
    )

    rerun_latest_pull_request_workflow(GitHub(), PULL_REQUEST_NUMBER)
    process_command(
        GitHub(),
        CommandRequest(COMMAND_COMMENT_ID, "/qg status", "admin", PULL_REQUEST_NUMBER),
    )

    state = fake_state()
    assert state["rerun_requests"] == [999]
    comment = next(
        item for item in state_objects(state, "comments") if item.get("id") == COMMAND_COMMENT_ID
    )
    assert [reaction.get("content") for reaction in state_objects(comment, "reactions")] == [
        "hooray"
    ]


def test_source_gate_failure_does_not_publish_a_stale_comment() -> None:
    """Leave the shared dashboard untouched when source collection raises."""
    path = f"/repos/{REPOSITORY}/pulls/{PULL_REQUEST_NUMBER}"
    reset_fake_github(
        {
            "failures": cast(
                "JsonValue",
                [{"method": "GET", "path": path, "status": SERVICE_UNAVAILABLE}],
            )
        }
    )

    with pytest.raises(GitHubAPIError):
        ScenarioCheck([]).run_pull_request_gate(
            GitHub(), pull_request_event(), JobResultPublisher()
        )

    assert state_objects(fake_state(), "comments") == []


def test_missing_pull_request_does_not_publish_a_stale_comment() -> None:
    """Leave the shared dashboard untouched when the pull request disappeared."""
    reset_fake_github({"pulls": []})

    with pytest.raises(RuntimeError, match="Pull request #7 was not found"):
        ScenarioCheck([]).run_pull_request_gate(
            GitHub(), pull_request_event(), JobResultPublisher()
        )

    assert state_objects(fake_state(), "comments") == []


def test_repository_client_surfaces_transport_failure() -> None:
    """Convert a real connection failure into the reusable client error contract."""
    with environment({"GITHUB_API_URL": "http://127.0.0.1:1"}):
        github = GitHub()
        with pytest.raises(RuntimeError, match="GitHub API GET /pulls/7 failed"):
            github.request("GET", f"/pulls/{PULL_REQUEST_NUMBER}")


def test_concrete_source_gates_scan_repository_contents_over_http() -> None:
    """Run both source gates against changed files served by the fake repository."""
    object_source = "value: object\n"
    suppression_source = "value = 1  # noqa\n"
    reset_fake_github(
        {
            "pull_files": {
                str(PULL_REQUEST_NUMBER): [
                    {
                        "filename": "example.py",
                        "status": "modified",
                        "patch": "@@ -0,0 +1 @@\n+value: object",
                    },
                    {
                        "filename": "suppressed.py",
                        "status": "modified",
                        "patch": "@@ -0,0 +1 @@\n+value = 1  # noqa",
                    },
                ]
            },
            "contents": {
                "head-sha:example.py": object_source,
                "head-sha:suppressed.py": suppression_source,
                "base-sha:example.py": "",
                "base-sha:suppressed.py": "",
            },
        }
    )

    assert object_annotations_main() == 1
    assert suppressions_main() == 1
    state = fake_state()
    labels = set(array_value(state["labels"], "labels"))
    assert "monori-object-annotation-failed" in labels
    assert "monori-suppression-failed" in labels


def test_object_gate_handles_unpatched_renames_and_skips_irrelevant_files(
    tmp_path: Path,
) -> None:
    """Compare renamed Python files when GitHub omits their patch."""
    reset_fake_github(
        {
            "pull_files": {
                str(PULL_REQUEST_NUMBER): [
                    {"filename": "removed.py", "status": "removed", "patch": ""},
                    {"filename": "README.md", "status": "modified", "patch": ""},
                    {
                        "filename": "renamed.py",
                        "previous_filename": "old.py",
                        "status": "renamed",
                    },
                ]
            },
            "contents": {
                "head-sha:renamed.py": "value: object\n",
                "base-sha:old.py": "value: str\n",
            },
        }
    )

    summary_path = tmp_path / "summary.md"
    with environment({"GITHUB_STEP_SUMMARY": str(summary_path)}):
        assert object_annotations_main() == 1
    assert "renamed.py:1" in summary_path.read_text()


def test_object_gate_reports_missing_comparison_as_infrastructure_failure() -> None:
    """Raise an infrastructure failure without overwriting the shared dashboard."""
    reset_fake_github(
        {
            "pull_files": {
                str(PULL_REQUEST_NUMBER): [
                    {"filename": "example.py", "status": "modified", "patch": ""}
                ]
            },
            "comparisons": {},
        }
    )

    with pytest.raises(RuntimeError, match="Cannot determine merge base"):
        object_annotations_main()

    assert state_objects(fake_state(), "comments") == []
