"""Exercise Quality Graph orchestration through the real GitHub HTTP client."""

from __future__ import annotations

import json
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, cast, override

import httpx
import pytest

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
from monori.ci.quality_graph.models import CheckContext, CheckResult, Verdict
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
    def error_annotation(self, finding: ScenarioFinding) -> str:
        """Render one workflow annotation for an active scenario finding."""
        return f"::error file={finding.path}::{finding.finding_id}"

    @override
    def rerun(self, github: RepositoryGitHubAPI, number: int) -> None:
        """Rerun the latest fake workflow when an approval changes."""
        rerun_latest_pull_request_workflow(github, number)


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


def test_source_gate_converges_labels_and_updates_one_report_comment() -> None:
    """Publish red and green runs without duplicating the managed report."""
    reset_fake_github()
    github = GitHub()

    failed = ScenarioCheck([ScenarioFinding("finding-1", "example.py")])
    assert failed.run_pull_request_gate(github, pull_request_event()) == 1
    after_failure = fake_state()
    assert after_failure["issue_labels"] == {str(PULL_REQUEST_NUMBER): [FAILURE_LABEL]}

    passed = ScenarioCheck([])
    assert passed.run_pull_request_gate(github, pull_request_event()) == 0
    after_success = fake_state()
    report_comments = [
        comment
        for comment in state_objects(after_success, "comments")
        if "<!-- monori-report: object-annotations -->"
        in string_value(comment.get("body"), "comment body")
    ]
    assert after_success["issue_labels"] == {str(PULL_REQUEST_NUMBER): []}
    assert len(report_comments) == 1
    assert "0 findings" in string_value(report_comments[0].get("body"), "comment body")


def test_pending_admin_command_is_reacted_to_consumed_and_rerun() -> None:
    """Apply an administrator command through reactions and pending approval state."""
    bundle_report: dict[str, JsonValue] = {
        "id": BUNDLE_REPORT_COMMENT_ID,
        "issue_number": PULL_REQUEST_NUMBER,
        "body": "<!-- monori-report: bundle-size -->\n\nBundle report\n",
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
    pull_body = string_value(pull.get("body"), "pull request body")
    report_body = string_value(report.get("body"), "report body")
    reactions = state_objects(command, "reactions")
    assert "monori-bundle-size-pending" in pull_body
    assert "monori-qg-authorized: bundle" in report_body
    assert [reaction.get("content") for reaction in reactions] == ["hooray"]
    assert armed["rerun_requests"] == [99]

    sync = BundleSizeCheck().sync_pending_approvals(
        GitHub(),
        PULL_REQUEST_NUMBER,
        pull_body,
        [BundleFinding("bundle-initial-load")],
    )
    consumed = fake_state()
    consumed_pull = state_objects(consumed, "pulls")[0]
    consumed_report = next(
        comment
        for comment in state_objects(consumed, "comments")
        if comment.get("id") == BUNDLE_REPORT_COMMENT_ID
    )
    consumed_pull_body = string_value(consumed_pull.get("body"), "pull request body")
    consumed_report_body = string_value(consumed_report.get("body"), "report body")
    assert sync.approved == {"bundle-initial-load"}
    assert "monori-bundle-size-pending" not in consumed_pull_body
    assert "monori-bundle-size-approvals: bundle-initial-load" in consumed_pull_body
    assert "monori-qg-authorized" not in consumed_report_body


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
    report_path.write_text(json.dumps(report_data))
    with environment({"REPORT_PATH": str(report_path), "SUMMARY_PATH": str(summary_path)}):
        reset_fake_github()
        assert bundle_size_main() == 1
        upsert_comment(GitHub(), PULL_REQUEST_NUMBER, "bundle-size", summary_path.read_text())
        state = fake_state()
        report = next(
            comment
            for comment in state_objects(state, "comments")
            if "monori-report: bundle-size" in str(comment.get("body"))
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
        upsert_comment(GitHub(), PULL_REQUEST_NUMBER, "bundle-size", summary_path.read_text())
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
    with environment({"GITHUB_EVENT_PATH": str(event_path)}):
        assert suppressions_main() == 1

    state = fake_state()
    pull = state_objects(state, "pulls")[0]
    body = string_value(pull.get("body"), "pull request body")
    approvals = SUPPRESSION_APPROVALS.read(body)
    report = next(
        comment
        for comment in state_objects(state, "comments")
        if "monori-report: suppression" in str(comment.get("body"))
    )
    report_body = string_value(report.get("body"), "suppression report")
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
    report = {
        "id": BUNDLE_REPORT_COMMENT_ID,
        "issue_number": PULL_REQUEST_NUMBER,
        "body": "<!-- monori-report: bundle-size -->\n\nBundle report\n",
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
            "done",
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
    assert github.request("DELETE", f"/issues/{PULL_REQUEST_NUMBER}/labels/missing") is None

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


def test_source_gate_failure_replaces_pending_report() -> None:
    """Publish a failed report when source collection raises after entering progress."""
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
        ScenarioCheck([]).run_pull_request_gate(GitHub(), pull_request_event())

    state = fake_state()
    report = next(
        comment
        for comment in state_objects(state, "comments")
        if "monori-report: object-annotations" in str(comment.get("body"))
    )
    body = string_value(report.get("body"), "failed report")
    assert body.startswith("<!-- monori-report: object-annotations -->\n\n## ❌")
    assert "The check stopped before it could produce a report." in body
    assert "In progress" not in body


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
