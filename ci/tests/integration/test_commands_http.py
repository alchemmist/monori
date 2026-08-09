"""Exercise Quality Graph commands through the GitHub HTTP client."""

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
    QualityGraphCommand,
    command_request,
    encode_command,
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
    command = QualityGraphCommand("ignore", ("bundle",))
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
