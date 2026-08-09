"""Test the compact Quality Graph dashboard model and renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from monori.ci.quality_graph.dashboard import (
    DashboardControlGroup,
    DashboardJob,
    DashboardModel,
    api_job_status,
    dashboard_metric,
    dashboard_status,
    load_results,
    refresh_running_jobs,
    render_dashboard,
)
from monori.ci.quality_graph.job_results import (
    JobControl,
    JobMetric,
    JobResult,
    JobStatus,
    write_job_result,
)
from monori.ci.quality_graph.registry import workflow_jobs

if TYPE_CHECKING:
    from pathlib import Path

    from monori.common import JsonValue


def test_dashboard_renders_status_links_metrics_and_controls() -> None:
    """Keep the PR comment compact while retaining navigation and actions."""
    control = JobControl("/qg ignore bundle", "/qg remove-ignore bundle-a")
    body = render_dashboard(
        DashboardModel(
            JobStatus.FAILED,
            "Detailed reports are available.",
            12,
            2,
            "head-sha",
            (
                DashboardJob(
                    "bundle-size",
                    "Frontend bundle size",
                    JobStatus.FAILED,
                    "https://example.test/run#bundle-size",
                    "https://example.test/job",
                    "Active: 1",
                ),
            ),
            (DashboardControlGroup("bundle-size", "Frontend bundle size", (control,)),),
        )
    )

    assert body.startswith("<!-- monori-qg-run: 12:2:head-sha -->")
    assert "## ❌ Quality Graph" in body
    assert "[Summary](https://example.test/run#bundle-size)" in body
    assert "[Logs](https://example.test/job)" in body
    assert f"<!-- {control.marker} -->" in body
    assert "<details><summary>For administrators</summary>" in body
    assert "### Frontend bundle size" in body


def test_dashboard_renderer_normalizes_blank_lines_and_final_newline() -> None:
    """Produce stable Markdown when dashboard messages contain extra spacing."""
    body = render_dashboard(
        DashboardModel(
            JobStatus.PASSED,
            "first\n\n\nsecond",
            12,
            1,
            "head-sha",
            (),
        )
    )

    assert "first\n\nsecond" in body
    assert "\n\n\n" not in body
    assert body.endswith("\n")
    assert not body.endswith("\n\n")


def test_dashboard_status_prefers_pending_then_failure() -> None:
    """Represent running work before rendering a final failure verdict."""
    pending = DashboardJob("a", "A", JobStatus.IN_PROGRESS, "summary", "logs")
    failed = DashboardJob("b", "B", JobStatus.FAILED, "summary", "logs")
    passed = DashboardJob("c", "C", JobStatus.PASSED, "summary", "logs")
    waiting = DashboardJob("d", "D", JobStatus.WAITING, "summary", "logs")

    assert dashboard_status((failed, pending)) is JobStatus.IN_PROGRESS
    assert dashboard_status((failed, passed)) is JobStatus.FAILED
    assert dashboard_status((passed,)) is JobStatus.PASSED
    assert dashboard_status((waiting, passed)) is JobStatus.IN_PROGRESS


def test_dashboard_metric_escapes_markdown_table_delimiters() -> None:
    """Keep result-provided labels and values inside one dashboard table cell."""
    result = JobResult(
        "lint",
        "Lint",
        JobStatus.PASSED,
        metrics=(JobMetric("Rules | checked", "10 | 10"),),
    )

    assert dashboard_metric(result) == "Rules &#124; checked: 10 &#124; 10"


def test_dashboard_metric_is_bounded_and_has_an_empty_placeholder() -> None:
    """Show at most two ordered metrics and a stable placeholder otherwise."""
    result = JobResult(
        "coverage",
        "Coverage",
        JobStatus.PASSED,
        metrics=(
            JobMetric("Lines", "99%"),
            JobMetric("Branches", "98%"),
            JobMetric("Ignored", "97%"),
        ),
    )

    assert dashboard_metric(None) == "—"
    assert dashboard_metric(JobResult("build", "Build", JobStatus.PASSED)) == "—"
    assert dashboard_metric(result) == "Lines: 99% · Branches: 98%"


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
