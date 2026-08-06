"""Test portable Quality Graph job results."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest

from monori.ci.quality_graph.job_report import build_result, parse_diagnostics
from monori.ci.quality_graph.job_report import main as job_report_main
from monori.ci.quality_graph.job_results import (
    AnnotationLevel,
    JobControl,
    JobResult,
    JobStatus,
    SourceAnnotation,
    append_job_summary,
    controls_from_markdown,
    grouped_annotations,
    read_job_result,
    workflow_annotation_command,
    write_job_result,
)
from monori.ci.quality_graph.result_cli import main as result_cli_main

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@contextmanager
def arguments(values: list[str]) -> Iterator[None]:
    """Temporarily replace command-line arguments for one CLI test."""
    previous = sys.argv
    sys.argv = values
    try:
        yield
    finally:
        sys.argv = previous


@contextmanager
def environment(values: dict[str, str]) -> Iterator[None]:
    """Temporarily set environment values for one CLI test."""
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_job_result_round_trips_through_json(tmp_path: Path) -> None:
    """Preserve dashboard, summary, annotation, and control data between jobs."""
    result = JobResult(
        "lint",
        "Lint",
        JobStatus.FAILED,
        "Complete diagnostics",
        annotations=(SourceAnnotation("example.py", 2, 2, "broken"),),
        controls=(JobControl("/qg ignore object-a", "/qg remove-ignore object-a"),),
    )
    path = tmp_path / "result.json"

    write_job_result(path, result)

    assert read_job_result(path) == result


def test_grouped_annotations_merge_one_location_and_apply_limit() -> None:
    """Avoid noisy repeated annotations while retaining every source location."""
    annotations = [
        SourceAnnotation("same.py", 1, 1, "first"),
        SourceAnnotation("same.py", 1, 1, "second"),
        *(SourceAnnotation(f"file-{index}.py", 1, 1, "failure") for index in range(20)),
    ]

    grouped = grouped_annotations(annotations)

    assert len(grouped) == 10
    assert grouped[0].message == "first\nsecond"


def test_control_markers_restore_reversible_checkbox_state() -> None:
    """Recover both commands from a rendered administrator checkbox."""
    control = JobControl(
        "/qg ignore suppression-a",
        "/qg remove-ignore suppression-a",
        checked=True,
    )
    body = f"- [x] `{control.command}` <!-- {control.marker} -->"

    assert controls_from_markdown(body) == (control,)


def test_common_diagnostics_become_source_annotations() -> None:
    """Parse Python and frontend diagnostic locations from a make command log."""
    annotations = parse_diagnostics(
        "server/app.py:4:7: invalid type\nweb/src/app.tsx(8,2): unsafe call"
    )

    assert [(item.path, item.start_line, item.start_column) for item in annotations] == [
        ("server/app.py", 4, 7),
        ("web/src/app.tsx", 8, 2),
    ]


def test_failed_make_result_keeps_diagnostics_in_detailed_summary() -> None:
    """Keep full command output in the job summary while exposing compact metrics."""
    result = build_result("lint", "Lint", 1, "example.py:2: failure")

    assert result.status is JobStatus.FAILED
    assert result.annotations[0].level is AnnotationLevel.FAILURE
    assert "example.py:2: failure" in result.summary


def test_workflow_command_escapes_untrusted_annotation_data() -> None:
    """Prevent source diagnostics from breaking GitHub workflow command syntax."""
    rendered = workflow_annotation_command(
        SourceAnnotation("a,b.py", 1, 1, "line one\nline two", title="bad:title")
    )

    assert "file=a%2Cb.py" in rendered
    assert "title=bad%3Atitle" in rendered
    assert "line one%0Aline two" in rendered


def test_job_summary_has_a_stable_heading(tmp_path: Path) -> None:
    """Create the stable heading linked from the compact dashboard."""
    path = tmp_path / "summary.md"

    append_job_summary(path, JobResult("coverage", "Coverage", JobStatus.PASSED))

    assert path.read_text().startswith(
        '<a id="quality-graph-coverage"></a>\n\n## ✅ Quality Graph · coverage\n'
    )


def test_result_cli_writes_summary_metrics_and_artifact(tmp_path: Path) -> None:
    """Publish a simple composite-action result through the real CLI boundary."""
    output = tmp_path / "result.json"
    summary = tmp_path / "summary.md"
    with (
        environment({"GITHUB_STEP_SUMMARY": str(summary)}),
        arguments(
            [
                "result-cli",
                "--check-id",
                "mutation",
                "--title",
                "Mutation testing",
                "--status",
                "failed",
                "--message",
                "A mutant survived.",
                "--metric",
                "Score=80%",
                "--output",
                str(output),
            ]
        ),
    ):
        assert result_cli_main() == 0

    result = read_job_result(output)
    assert result.status is JobStatus.FAILED
    assert result.metrics[0].value == "80%"
    assert "A mutant survived." in summary.read_text()


def test_result_cli_rejects_malformed_metric(tmp_path: Path) -> None:
    """Reject metrics that cannot be represented by the typed result model."""
    with (
        arguments(
            [
                "result-cli",
                "--check-id",
                "build",
                "--title",
                "Build",
                "--status",
                "passed",
                "--metric",
                "missing-separator",
                "--output",
                str(tmp_path / "result.json"),
            ]
        ),
        pytest.raises(SystemExit),
    ):
        result_cli_main()


def test_job_report_cli_reads_a_real_log_and_emits_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Convert one captured make log through the production CLI entrypoint."""
    log = tmp_path / "lint.log"
    output = tmp_path / "lint.json"
    summary = tmp_path / "summary.md"
    log.write_text("example.py:3:2: invalid type\n")
    with arguments(
        [
            "job-report",
            "--check-id",
            "lint",
            "--title",
            "Lint",
            "--exit-code",
            "1",
            "--log",
            str(log),
            "--output",
            str(output),
            "--summary",
            str(summary),
        ]
    ):
        assert job_report_main() == 0

    assert read_job_result(output).status is JobStatus.FAILED
    assert "::error file=example.py,line=3" in capsys.readouterr().err
