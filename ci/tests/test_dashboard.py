"""Test the compact Quality Graph dashboard model and renderer."""

from pathlib import Path
from typing import TYPE_CHECKING

from monori.ci.quality_graph.dashboard import (
    EMPTY_CONTROLS_MESSAGE,
    DashboardControlGroup,
    DashboardJob,
    DashboardModel,
    dashboard_status,
    load_results,
    refresh_dashboard_body,
    render_dashboard,
)
from monori.ci.quality_graph.job_results import (
    JobControl,
    JobResult,
    JobStatus,
    write_job_result,
)

if TYPE_CHECKING:
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


def test_dashboard_status_prefers_pending_then_failure() -> None:
    """Represent running work before rendering a final failure verdict."""
    pending = DashboardJob("a", "A", JobStatus.PENDING, "summary", "logs")
    failed = DashboardJob("b", "B", JobStatus.FAILED, "summary", "logs")
    passed = DashboardJob("c", "C", JobStatus.PASSED, "summary", "logs")

    assert dashboard_status((failed, pending)) is JobStatus.PENDING
    assert dashboard_status((failed, passed)) is JobStatus.FAILED
    assert dashboard_status((passed,)) is JobStatus.PASSED


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


def test_live_refresh_updates_completed_and_api_reported_rows() -> None:
    """Reflect job completion before the final dashboard aggregation runs."""
    body = render_dashboard(
        DashboardModel(
            JobStatus.PENDING,
            "The current Quality Graph run is in progress.",
            12,
            1,
            "head-sha",
            (
                DashboardJob(
                    "workflow-graph",
                    "Workflow graph validation",
                    JobStatus.PENDING,
                    "summary",
                    "logs",
                ),
                DashboardJob("fmt-check", "Format check", JobStatus.PENDING, "summary", "logs"),
            ),
        )
    )
    api_jobs: dict[str, dict[str, JsonValue]] = {
        "Workflow graph validation": {"status": "completed", "conclusion": "success"},
        "Format check": {"status": "in_progress", "conclusion": None},
    }

    refreshed = refresh_dashboard_body(
        body,
        JobResult("fmt-check", "Format check", JobStatus.PASSED),
        api_jobs,
    )

    assert "| Workflow graph validation | ✅ passed |" in refreshed
    assert "| Format check | ✅ passed |" in refreshed
    assert "## ⏳ Quality Graph" in refreshed


def test_live_refresh_adds_and_removes_job_admin_controls() -> None:
    """Keep failed-job checkboxes grouped under the administrator disclosure."""
    body = render_dashboard(
        DashboardModel(
            JobStatus.PENDING,
            "The current Quality Graph run is in progress.",
            12,
            1,
            "head-sha",
            (
                DashboardJob(
                    "suppressions",
                    "Lint suppression gate",
                    JobStatus.PENDING,
                    "summary",
                    "logs",
                ),
            ),
        )
    )
    control = JobControl(
        "/qg ignore suppression-abc123",
        "/qg remove-ignore suppression-abc123",
    )

    failed = refresh_dashboard_body(
        body,
        JobResult(
            "suppressions",
            "Lint suppression gate",
            JobStatus.FAILED,
            controls=(control,),
        ),
        {},
    )

    assert "<details><summary>For administrators</summary>" in failed
    assert "### Lint suppression gate" in failed
    assert "- [ ] `/qg ignore suppression-abc123`" in failed
    assert EMPTY_CONTROLS_MESSAGE not in failed

    passed = refresh_dashboard_body(
        failed,
        JobResult("suppressions", "Lint suppression gate", JobStatus.PASSED),
        {},
    )

    assert "### Lint suppression gate" not in passed
    assert EMPTY_CONTROLS_MESSAGE in passed
