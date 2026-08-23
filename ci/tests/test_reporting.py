"""Tests for shared Quality Graph report and reaction lifecycles."""

import re

import pytest

from monori.ci.lib.comments import (
    GITHUB_COMMENT_BODY_LIMIT,
    bounded_comment_body,
)
from monori.ci.quality_graph.job_results import JobControl
from monori.ci.quality_graph.models import Metric
from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID, workflow_job_for_report
from monori.ci.quality_graph.reporting import (
    AdminCommands,
    ReportFinding,
    ReportModel,
    ReportStatus,
    admin_commands,
    finding_location,
    render_report,
)


def test_renderer_owns_status_heading_findings_and_admin_commands() -> None:
    """Render the complete common report frame from typed gate data."""
    report = render_report(
        ReportModel(
            "suppression",
            ReportStatus.FAILED,
            metrics=(Metric("Active", "1"),),
            findings=(
                ReportFinding(
                    "`example-1`",
                    location=finding_location(
                        "https://github.com/org/repo/pull/1", "example.py", 1
                    ),
                ),
            ),
            admin=admin_commands(
                "suppression",
                ["example-1"],
                [],
                {"example.py": ["example-1"]},
            ),
        )
    )

    body = report.summary
    assert (
        report.controls
        == admin_commands(
            "suppression",
            ["example-1"],
            [],
            {"example.py": ["example-1"]},
        ).controls
    )
    assert body.startswith("## ❌ Lint suppression gate\n")
    assert "| Active | 1 |" in body
    assert "<details><summary>Findings (1)</summary>" in body
    assert "[`example.py:1`](https://github.com/org/repo/pull/1/files#diff-" in body
    assert "`/qg ignore example-1`" in body
    assert "`/qg ignore suppressions`" in body
    assert "`/qg ignore-file example.py`" in body


def test_file_control_reverses_only_findings_from_its_file() -> None:
    """Keep each file checkbox reverse command scoped to the same file."""
    commands = admin_commands(
        "suppression",
        ["suppression-a", "suppression-b", "suppression-c"],
        [],
        {
            "a.py": ["suppression-a", "suppression-b"],
            "b.py": ["suppression-c"],
        },
    )

    file_controls = [control for control in commands.controls if "ignore-file" in control.command]

    assert [(control.command, control.reverse_command) for control in file_controls] == [
        ("/qg ignore-file a.py", "/qg remove-ignore suppression-a,suppression-b"),
        ("/qg ignore-file b.py", "/qg remove-ignore suppression-c"),
    ]


def test_admin_commands_preserve_all_ids_notes_and_reverse_operations() -> None:
    """Build deterministic controls without dropping command state."""
    commands = admin_commands(
        "suppression",
        ["suppression-b", "suppression-a"],
        ["suppression-d", "suppression-c"],
        notes=["Repository administrators only."],
    )

    assert commands == AdminCommands(
        (
            JobControl(
                "/qg ignore suppression-a,suppression-b",
                "/qg remove-ignore suppression-a,suppression-b",
            ),
            JobControl(
                "/qg ignore suppressions",
                "/qg remove-ignore suppression-a,suppression-b",
            ),
            JobControl(
                "/qg ignore suppression-c,suppression-d",
                "/qg remove-ignore suppression-c,suppression-d",
                checked=True,
            ),
        ),
        ("Repository administrators only.",),
    )


def test_renderer_normalizes_blank_lines_and_ends_with_one_newline() -> None:
    """Keep rendered report Markdown stable for comments and summaries."""
    report = render_report(
        ReportModel("bundle-size", ReportStatus.PASSED, content="first\n\n\nsecond")
    )
    body = report.summary

    assert "first\n\nsecond" in body
    assert "\n\n\n" not in body
    assert body.endswith("\n")
    assert not body.endswith("\n\n")


def test_unknown_report_marker_has_an_actionable_error() -> None:
    """Identify an unregistered report marker in renderer failures."""
    with pytest.raises(ValueError, match="Unknown Quality Graph report marker: missing"):
        render_report(ReportModel("missing", ReportStatus.FAILED))


def test_comment_body_is_bounded_with_an_exact_omission_notice() -> None:
    """Keep oversized reports within GitHub's hard comment-body limit."""
    original = "x" * (GITHUB_COMMENT_BODY_LIMIT + 500)

    bounded = bounded_comment_body(original)

    assert len(bounded) == GITHUB_COMMENT_BODY_LIMIT
    match = re.search(r"(\d+) characters omitted", bounded)
    assert match is not None
    notice_start = bounded.index("\n\n_Report truncated;")
    assert int(match.group(1)) == len(original) - notice_start


def test_empty_admin_commands_do_not_instruct_the_reader_to_post() -> None:
    """Avoid contradictory command instructions for a passing report."""
    report = render_report(
        ReportModel("bundle-size", ReportStatus.PASSED, admin=admin_commands("bundle", [], []))
    )
    body = report.summary

    assert "No actionable findings in this run." in body
    assert "Post exactly one command" not in body


def test_report_metadata_comes_from_the_workflow_registry() -> None:
    """Resolve report titles and markers from the canonical workflow definition."""
    assert workflow_job_for_report("suppression") is WORKFLOW_JOB_BY_ID["suppressions"]
