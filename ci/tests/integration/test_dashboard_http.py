"""Exercise the Quality Graph dashboard through the GitHub HTTP client."""

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
from monori.ci.quality_graph.registry import workflow_jobs
from monori.ci.quality_graph.reporting import RenderedCheckReport
from monori.common import JsonValue, array_value, object_value, string_value

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from monori.ci.lib.github import RepositoryGitHubAPI

from monori.ci.tests.integration.quality_graph_http_support import (
    BUNDLE_REPORT_COMMENT_ID,
    COMMAND_COMMENT_ID,
    FAILURE_LABEL,
    PULL_REQUEST_NUMBER,
    REPOSITORY,
    SERVICE_UNAVAILABLE,
    ScenarioCheck,
    ScenarioFinding,
    arguments,
    checkbox_body,
    checkbox_event,
    environment,
    fake_state,
    pull_request_event,
    reset_fake_github,
    result_control_body,
    state_objects,
)

pytestmark = pytest.mark.integration


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


def test_dashboard_watcher_does_not_patch_an_unchanged_comment() -> None:
    """Avoid content writes when one polling iteration observes no status changes."""
    reset_fake_github(
        {
            "workflow_jobs": {
                "99": [
                    {
                        "name": "Workflow graph validation",
                        "status": "in_progress",
                        "conclusion": None,
                        "html_url": "https://example.test/jobs/workflow-graph",
                    }
                ]
            }
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
    state = fake_state()
    dashboard = state_objects(state, "comments")[0]
    dashboard_id = dashboard.get("id")
    assert isinstance(dashboard_id, int)
    state["failures"] = [
        {
            "method": "PATCH",
            "path": f"/repos/{REPOSITORY}/issues/comments/{dashboard_id}",
            "status": SERVICE_UNAVAILABLE,
        }
    ]
    reset_fake_github(state)

    with pytest.raises(TimeoutError):
        lifecycle.watch(0, 0.01)


def test_dashboard_watcher_stays_within_request_budget_without_noop_patches() -> None:
    """Measure polling traffic instead of relying only on the configured interval."""
    reset_fake_github(
        {
            "workflow_jobs": {
                "99": [
                    {
                        "name": "Workflow graph validation",
                        "status": "in_progress",
                        "conclusion": None,
                        "html_url": "https://example.test/jobs/workflow-graph",
                    }
                ]
            }
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
    state = fake_state()
    dashboard = state_objects(state, "comments")[0]
    comment_id = dashboard.get("id")
    assert isinstance(comment_id, int)
    reset_fake_github(state)

    iterations = 3
    for _ in range(iterations):
        assert not lifecycle.refresh_once(comment_id)

    requests = state_objects(fake_state(), "requests")
    projected_requests_per_hour = len(requests) / iterations * 60 * 60 / DEFAULT_WATCH_INTERVAL
    comment_patch_count = sum(
        request.get("method") == "PATCH"
        and request.get("path") == f"/repos/{REPOSITORY}/issues/comments/{comment_id}"
        for request in requests
    )
    assert projected_requests_per_hour <= 500
    assert comment_patch_count == 0


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


def test_checkbox_edit_wins_over_concurrent_watcher_refresh() -> None:
    """Restore an administrator edit after an already-running watcher writes stale state."""
    control = JobControl(
        "/qg ignore bundle-initial-load",
        "/qg remove-ignore bundle-initial-load",
    )
    body = render_dashboard(
        DashboardModel(
            JobStatus.IN_PROGRESS,
            "Running",
            99,
            1,
            "head-sha",
            (
                DashboardJob(
                    "workflow-graph",
                    "Workflow graph validation",
                    JobStatus.WAITING,
                    "https://example.test/summary",
                    "https://example.test/logs",
                ),
            ),
            (DashboardControlGroup("bundle-size", "Frontend bundle size", (control,)),),
        )
    )
    reset_fake_github(
        {
            "workflow_jobs": {
                "99": [
                    {
                        "name": "Workflow graph validation",
                        "status": "in_progress",
                        "conclusion": None,
                        "html_url": "https://example.test/jobs/workflow-graph",
                    }
                ]
            }
        }
    )
    upsert_comment(GitHub(), PULL_REQUEST_NUMBER, "quality-graph", body)
    state = fake_state()
    report = state_objects(state, "comments")[0]
    report_id = report.get("id")
    assert isinstance(report_id, int)
    unchecked = string_value(report.get("body"), "dashboard body")
    checked = checkbox_body(unchecked, checked=True)
    delays: JsonValue = [
        {
            "method": "PATCH",
            "path": f"/repos/{REPOSITORY}/issues/comments/{report_id}",
            "seconds": 0.5,
        }
    ]
    state["request_delays"] = delays
    reset_fake_github(state)
    lifecycle = DashboardLifecycle(
        GitHub(),
        PULL_REQUEST_NUMBER,
        99,
        1,
        "head-sha",
        "https://example.test/runs/99",
    )
    watcher = threading.Thread(target=lifecycle.refresh_once, args=(report_id,))
    watcher.start()
    patch_path = f"/repos/{REPOSITORY}/issues/comments/{report_id}"
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        requests = state_objects(fake_state(), "requests")
        if any(
            request.get("method") == "PATCH" and request.get("path") == patch_path
            for request in requests
        ):
            break
        time.sleep(0.01)
    else:
        message = "Watcher did not reach the delayed dashboard update"
        raise AssertionError(message)
    GitHub().request("PATCH", f"/issues/comments/{report_id}", {"body": checked})
    watcher.join(timeout=2)
    assert not watcher.is_alive()
    new_control = JobControl("/qg ignore bundle-other", "/qg remove-ignore bundle-other")
    latest = state_objects(fake_state(), "comments")[0]
    latest_body = string_value(latest.get("body"), "dashboard body")
    new_line = f"- [ ] `{new_control.command}` <!-- {new_control.marker} -->\n"
    latest_body = latest_body.replace(
        "<!-- monori-qg-controls:end -->", new_line + "\n<!-- monori-qg-controls:end -->"
    )
    GitHub().request("PATCH", f"/issues/comments/{report_id}", {"body": latest_body})

    request = command_request(checkbox_event(report_id, checked, unchecked))
    assert request is not None
    process_command(GitHub(), request)
    armed = fake_state()
    dashboard = next(
        comment for comment in state_objects(armed, "comments") if comment.get("id") == report_id
    )
    dashboard_body = string_value(dashboard.get("body"), "dashboard body")
    assert f"<!-- {control.marker} -->" in dashboard_body
    assert f"<!-- {new_control.marker} -->" in dashboard_body
    assert "- [x]" in dashboard_body
    pull = state_objects(armed, "pulls")[0]
    pull_body = string_value(pull.get("body"), "pull body")
    sync = BundleSizeCheck().sync_pending_approvals(
        GitHub(),
        PULL_REQUEST_NUMBER,
        pull_body,
        [BundleFinding("bundle-initial-load")],
    )
    assert sync.approved == {"bundle-initial-load"}
