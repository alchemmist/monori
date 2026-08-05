"""Tests for shared Quality Graph report and reaction lifecycles."""

import re

from monori.ci.lib.comments import (
    GITHUB_COMMENT_BODY_LIMIT,
    bounded_comment_body,
)
from monori.ci.quality_graph.reporting import (
    CHECK_REPORTS,
    SURFACE_REPORTS,
    ReportFinding,
    ReportMetric,
    ReportModel,
    ReportStatus,
    admin_commands,
    finding_location,
    render_report,
)


def test_renderer_owns_status_heading_findings_and_admin_commands() -> None:
    """Render the complete common report frame from typed gate data."""
    body = render_report(
        ReportModel(
            "suppression",
            ReportStatus.FAIL,
            metrics=(ReportMetric("Active", "1"),),
            findings=(
                ReportFinding(
                    "`example-1`",
                    location=finding_location(
                        "https://github.com/org/repo/pull/1", "example.py", 1
                    ),
                ),
            ),
            admin=admin_commands(
                "example",
                ["example-1"],
                [],
                {"example.py": ["example-1"]},
            ),
        )
    )

    assert body.startswith("## ❌ Lint suppression gate\n")
    assert "| Active | 1 |" in body
    assert "<details><summary>Findings (1)</summary>" in body
    assert "[`example.py:1`](https://github.com/org/repo/pull/1/files#diff-" in body
    assert "`/qg ignore example-1`" in body
    assert "`/qg ignore example`" in body
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
    body = render_report(
        ReportModel("bundle-size", ReportStatus.DONE, admin=admin_commands("bundle", [], []))
    )

    assert "No actionable findings in this run." in body
    assert "Post exactly one command" not in body


def test_check_and_command_surface_reports_have_separate_registries() -> None:
    """Keep command UI definitions out of the check report registry."""
    assert "quality-graph" in SURFACE_REPORTS
    assert "quality-graph" not in CHECK_REPORTS
    assert "suppression" in CHECK_REPORTS
