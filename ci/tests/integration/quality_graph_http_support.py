"""Exercise Quality Graph orchestration through the real GitHub HTTP client."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
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
    DEFAULT_WATCH_INTERVAL,
    DashboardControlGroup,
    DashboardJob,
    DashboardLifecycle,
    DashboardModel,
    mark_jobs_pending,
    render_dashboard,
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
from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID, workflow_jobs
from monori.ci.quality_graph.reporting import RenderedCheckReport
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

    definition = WORKFLOW_JOB_BY_ID["object-annotations"]
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
    ) -> RenderedCheckReport:
        """Render enough domain state to verify report replacement semantics."""
        return RenderedCheckReport(
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
