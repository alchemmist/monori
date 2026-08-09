"""Exercise reusable GitHub client helpers over HTTP."""

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
from monori.common import array_value, object_value, string_value

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from monori.ci.lib.github import RepositoryGitHubAPI
    from monori.common import JsonValue

from monori.ci.tests.integration.quality_graph_http_support import (
    BUNDLE_REPORT_COMMENT_ID,
    COMMAND_COMMENT_ID,
    FAILURE_LABEL,
    FAKE_GITHUB_URL,
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
