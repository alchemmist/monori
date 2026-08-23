"""Test Quality Graph dashboard rendering."""

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


def test_dashboard_limits_file_controls_without_breaking_admin_markdown() -> None:
    """Keep aggregate actions and structural markers when file controls exceed the limit."""
    aggregate = JobControl(
        "/qg ignore suppression",
        "/qg remove-ignore suppression",
    )
    file_controls = tuple(
        JobControl(
            f"/qg ignore-file server/package_{index:03d}/module_with_a_long_name.py",
            f"/qg remove-ignore suppression-{index:012d}",
        )
        for index in range(500)
    )
    body = render_dashboard(
        DashboardModel(
            JobStatus.FAILED,
            "Detailed reports are available.",
            12,
            1,
            "head-sha",
            (
                DashboardJob(
                    "suppressions",
                    "Lint suppression gate",
                    JobStatus.FAILED,
                    "https://example.test/run#suppressions",
                    "https://example.test/job",
                ),
            ),
            (
                DashboardControlGroup(
                    "suppressions",
                    "Lint suppression gate",
                    (aggregate, *file_controls),
                ),
            ),
        )
    )

    assert len(comment_body(DASHBOARD_MARKER, body)) <= GITHUB_COMMENT_BODY_LIMIT
    assert f"<!-- {aggregate.marker} -->" in body
    assert body.count("/qg ignore-file ") < len(file_controls)
    assert "additional actions are available" in body
    assert "[Lint suppression gate Job Summary](https://example.test/run#suppressions)" in body
    assert "<!-- monori-qg-controls:end -->" in body
    assert body.rstrip().endswith("</details>")


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
        metrics=(Metric("Rules | checked", "10 | 10"),),
    )

    assert dashboard_metric(result) == "Rules &#124; checked: 10 &#124; 10"


def test_dashboard_metric_is_bounded_and_has_an_empty_placeholder() -> None:
    """Show at most two ordered metrics and a stable placeholder otherwise."""
    result = JobResult(
        "coverage",
        "Coverage",
        JobStatus.PASSED,
        metrics=(
            Metric("Lines", "99%"),
            Metric("Branches", "98%"),
            Metric("Ignored", "97%"),
        ),
    )

    assert dashboard_metric(None) == "—"
    assert dashboard_metric(JobResult("build", "Build", JobStatus.PASSED)) == "—"
    assert dashboard_metric(result) == "Lines: 99% · Branches: 98%"
