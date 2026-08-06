"""Test the compact Quality Graph dashboard model and renderer."""

from pathlib import Path

from monori.ci.quality_graph.dashboard import (
    DashboardControlGroup,
    DashboardJob,
    DashboardModel,
    dashboard_status,
    load_results,
    render_dashboard,
)
from monori.ci.quality_graph.job_results import (
    JobControl,
    JobResult,
    JobStatus,
    write_job_result,
)


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
            (DashboardControlGroup("Frontend bundle size", (control,)),),
        )
    )

    assert body.startswith("<!-- monori-qg-run: 12:2:head-sha -->")
    assert "## ❌ Quality Graph" in body
    assert "[Summary](https://example.test/run#bundle-size)" in body
    assert "[Logs](https://example.test/job)" in body
    assert f"<!-- {control.marker} -->" in body


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
