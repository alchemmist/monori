"""Test Quality Graph dashboard state transitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from monori.ci.lib.comments import GITHUB_COMMENT_BODY_LIMIT, comment_body
from monori.ci.quality_graph.dashboard import (
    DASHBOARD_MARKER,
    DEFAULT_WATCH_INTERVAL,
    DashboardControlGroup,
    DashboardJob,
    DashboardModel,
    api_job_status,
    dashboard_metric,
    dashboard_status,
    latest_jobs_by_name,
    load_results,
    refresh_running_jobs,
    render_dashboard,
)
from monori.ci.quality_graph.job_results import (
    JobControl,
    JobResult,
    JobStatus,
    write_job_result,
)
from monori.ci.quality_graph.models import Metric
from monori.ci.quality_graph.registry import workflow_jobs

if TYPE_CHECKING:
    from pathlib import Path

    from monori.common import JsonValue


@pytest.mark.parametrize(
    ("job", "expected"),
    [
        ({"status": "queued", "conclusion": None}, JobStatus.WAITING),
        ({"status": "in_progress", "conclusion": None}, JobStatus.IN_PROGRESS),
        ({"status": "completed", "conclusion": "success"}, JobStatus.PASSED),
        ({"status": "completed", "conclusion": "skipped"}, JobStatus.SKIPPED),
        ({"status": "completed", "conclusion": "failure"}, JobStatus.FAILED),
    ],
)
def test_api_job_status_maps_every_actions_state(
    job: dict[str, JsonValue], expected: JobStatus
) -> None:
    """Map queued, running, and terminal Actions states without ambiguity."""
    assert api_job_status(job) is expected


def test_latest_jobs_by_name_prefers_the_newest_rerun_attempt() -> None:
    """Retain old successful jobs while replacing jobs present in a partial rerun."""
    jobs = latest_jobs_by_name(
        [
            {
                "id": 10,
                "name": "Format check",
                "run_attempt": 1,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "id": 11,
                "name": "Frontend bundle size",
                "run_attempt": 1,
                "status": "completed",
                "conclusion": "failure",
            },
            {
                "id": 20,
                "name": "Frontend bundle size",
                "run_attempt": 2,
                "status": "in_progress",
                "conclusion": None,
            },
        ]
    )

    assert jobs["Format check"]["id"] == 10
    assert jobs["Frontend bundle size"]["id"] == 20


def test_result_loader_merges_downloaded_artifact_directories(tmp_path: Path) -> None:
    """Index JSON results downloaded from isolated workflow jobs."""
    write_job_result(
        tmp_path / "artifact-a" / "lint.json",
        JobResult("lint", "Lint", JobStatus.PASSED),
    )
    write_job_result(
        tmp_path / "artifact-b" / "type.json",
        JobResult("type", "Type check", JobStatus.FAILED),
    )

    results = load_results(tmp_path)

    assert set(results) == {"lint", "type"}


def test_result_loader_keeps_latest_check_result_across_rerun_attempts(tmp_path: Path) -> None:
    """Preserve successful jobs while replacing rerun checks with their newest artifact."""
    write_job_result(
        tmp_path / "quality-result-object-annotations-1" / "object-annotations.json",
        JobResult(
            "object-annotations",
            "Python object annotation gate",
            JobStatus.PASSED,
            controls=(JobControl("/qg ignore object", "/qg remove-ignore object-a"),),
        ),
    )
    write_job_result(
        tmp_path / "quality-result-bundle-size-1" / "bundle-size.json",
        JobResult("bundle-size", "Frontend bundle size", JobStatus.FAILED),
    )
    write_job_result(
        tmp_path / "quality-result-bundle-size-2" / "bundle-size.json",
        JobResult("bundle-size", "Frontend bundle size", JobStatus.PASSED),
    )

    results = load_results(tmp_path)

    assert results["object-annotations"].controls[0].command == "/qg ignore object"
    assert results["bundle-size"].status is JobStatus.PASSED


def test_running_refresh_marks_current_job_and_observed_parallel_jobs() -> None:
    """Publish all current Actions states from the single live writer."""
    body = render_dashboard(
        DashboardModel(
            JobStatus.IN_PROGRESS,
            "The current Quality Graph run is in progress.",
            12,
            1,
            "head-sha",
            (
                DashboardJob(
                    "fmt-check",
                    "Format check",
                    JobStatus.WAITING,
                    "summary",
                    "run",
                ),
                DashboardJob(
                    "test-slow",
                    "Slow tests",
                    JobStatus.WAITING,
                    "summary",
                    "run",
                ),
            ),
        )
    )
    api_jobs: dict[str, dict[str, JsonValue]] = {
        "Format check": {
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://example.test/jobs/fmt",
        },
        "Slow tests": {
            "status": "in_progress",
            "conclusion": None,
            "html_url": "https://example.test/jobs/slow",
        },
    }

    refreshed = refresh_running_jobs(body, api_jobs, "https://example.test/run")

    assert "| Format check | ✅ passed |" in refreshed
    assert "[Logs](https://example.test/jobs/fmt)" in refreshed
    assert "| Slow tests | 🚀 in progress |" in refreshed
    assert "[Logs](https://example.test/jobs/slow)" in refreshed
    assert "## 🚀 Quality Graph" in refreshed


def test_running_refresh_publishes_a_terminal_dashboard_status() -> None:
    """Replace the pending heading after every registered job has passed."""
    body = render_dashboard(
        DashboardModel(
            JobStatus.IN_PROGRESS,
            "The current Quality Graph run is in progress.",
            12,
            1,
            "head-sha",
            tuple(
                DashboardJob(
                    definition.job_id,
                    definition.title,
                    JobStatus.WAITING,
                    "summary",
                    "run",
                )
                for definition in workflow_jobs().values()
            ),
        )
    )
    api_jobs: dict[str, dict[str, JsonValue]] = {
        definition.title: {
            "status": "completed",
            "conclusion": "success",
            "html_url": f"https://example.test/jobs/{definition.job_id}",
        }
        for definition in workflow_jobs().values()
    }

    refreshed = refresh_running_jobs(body, api_jobs, "https://example.test/run")

    assert "## ✅ Quality Graph" in refreshed
    assert "## 🚀 Quality Graph" not in refreshed
