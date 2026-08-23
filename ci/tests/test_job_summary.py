"""Test portable Quality Graph job summaries and result CLIs."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from io import StringIO
from typing import TYPE_CHECKING

import pytest

from monori.ci.lib.annotations import (
    MAX_STEP_ANNOTATIONS,
    AnnotationLevel,
    SourceAnnotation,
    escape_data,
    grouped_annotations,
    publish_workflow_annotations,
    workflow_annotation_command,
)
from monori.ci.lib.diagnostics import (
    COLON_RE,
    DiagnosticContext,
    annotation_from_match,
    normalize_source_path,
    parse_context_line,
    parse_diagnostics,
    parse_diff_annotations,
)
from monori.ci.quality_graph.job_report import (
    MAX_SUMMARY_LOG_CHARACTERS,
    build_result,
    diagnostic_summary,
)
from monori.ci.quality_graph.job_report import main as job_report_main
from monori.ci.quality_graph.job_results import (
    JobControl,
    JobResult,
    JobResultPublisher,
    JobStatus,
    append_job_summary,
    controls_from_markdown,
    read_job_result,
    write_job_result,
)
from monori.ci.quality_graph.models import Metric
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


def test_failed_make_result_keeps_diagnostics_in_detailed_summary() -> None:
    """Keep full command output in the job summary while exposing compact metrics."""
    result = build_result("lint", "Lint", 1, "example.py:2: failure")

    assert result.status is JobStatus.FAILED
    assert result.annotations[0].level is AnnotationLevel.FAILURE
    assert "example.py:2: failure" in result.summary


def test_diagnostic_summary_handles_empty_backticks_and_truncation() -> None:
    """Render safe bounded Markdown for every command-output shape."""
    assert diagnostic_summary("\x1b[31m  \x1b[0m", 0) == "No diagnostic output was produced."
    assert diagnostic_summary("failure with ``` inside", 2) == (
        "Detected source diagnostics: **2**\n\n"
        "<details><summary>Command output</summary>\n\n"
        "````text\nfailure with ``` inside\n````\n\n</details>"
    )
    oversized = "x" * (MAX_SUMMARY_LOG_CHARACTERS + 3)
    rendered = diagnostic_summary(oversized, 0)
    assert "x" * MAX_SUMMARY_LOG_CHARACTERS in rendered
    assert "x" * (MAX_SUMMARY_LOG_CHARACTERS + 1) not in rendered
    assert "_Output truncated; 3 characters remain available in the job log._" in rendered


def test_job_summary_has_a_stable_heading(tmp_path: Path) -> None:
    """Create the stable heading linked from the compact dashboard."""
    path = tmp_path / "summary.md"

    append_job_summary(path, JobResult("coverage", "Coverage", JobStatus.PASSED))

    assert path.read_text() == ('<a id="quality-graph-coverage"></a>\n\n## ✅ Coverage\n')


def test_result_publisher_uses_only_explicit_sinks(tmp_path: Path) -> None:
    """Ignore ambient GitHub paths unless the CLI explicitly supplies them."""
    ambient = tmp_path / "ambient.md"
    explicit = tmp_path / "explicit.md"
    result = JobResult("build", "Build", JobStatus.PASSED)

    with environment({"GITHUB_STEP_SUMMARY": str(ambient)}):
        JobResultPublisher().publish(result)
        JobResultPublisher(summary_path=explicit).publish(result)

    assert not ambient.exists()
    assert explicit.read_text() == '<a id="quality-graph-build"></a>\n\n## ✅ Build\n'


def test_complete_report_is_not_wrapped_in_a_duplicate_summary(tmp_path: Path) -> None:
    """Preserve a check-rendered heading and metrics without generic duplication."""
    result = JobResult(
        "suppressions",
        "Lint suppression gate",
        JobStatus.PASSED,
        "## ✅ Lint suppression gate\n\n| Metric | Value |\n| --- | ---: |\n| Status | PASS |\n",
        (Metric("Findings", "0"),),
    )
    path = tmp_path / "summary.md"
    append_job_summary(path, result)
    body = path.read_text()

    assert body.count("## ✅ Lint suppression gate") == 1
    assert "Quality Graph ·" not in body
    assert body.count("| Metric | Value |") == 1


def test_job_summary_keeps_the_full_noninteractive_command_reference(tmp_path: Path) -> None:
    """Publish every command outside the size-constrained dashboard comment."""
    controls = tuple(
        JobControl(
            f"/qg ignore-file server/example_{index}.py",
            f"/qg remove-ignore suppression-{index}",
        )
        for index in range(500)
    )
    path = tmp_path / "summary.md"

    append_job_summary(
        path,
        JobResult("suppressions", "Lint suppression gate", JobStatus.FAILED, controls=controls),
    )

    body = path.read_text()
    assert "Administrative command reference (500)" in body
    assert "/qg ignore-file server/example_499.py" in body
    assert "/qg remove-ignore suppression-499" in body
    assert "- [ ]" not in body


def test_result_cli_writes_summary_metrics_and_artifact(tmp_path: Path) -> None:
    """Publish a simple composite-action result through the real CLI boundary."""
    output = tmp_path / "result.json"
    summary = tmp_path / "summary.md"
    with arguments(
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
            "--job-summary",
            str(summary),
        ]
    ):
        assert result_cli_main() == 0

    result = read_job_result(output)
    assert result == JobResult(
        "mutation",
        "Mutation testing",
        JobStatus.FAILED,
        "A mutant survived.",
        (Metric("Score", "80%"),),
    )
    assert summary.read_text() == (
        '<a id="quality-graph-mutation"></a>\n\n'
        "## ❌ Mutation testing\n\n"
        "| Metric | Value |\n"
        "| --- | ---: |\n"
        "| Score | 80% |\n\n"
        "A mutant survived.\n"
    )


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


@pytest.mark.parametrize("missing", ["--check-id", "--title", "--status", "--output"])
def test_result_cli_requires_its_public_contract(tmp_path: Path, missing: str) -> None:
    """Reject invocations that omit any required result field."""
    values = [
        "result-cli",
        "--check-id",
        "build",
        "--title",
        "Build",
        "--status",
        "passed",
        "--output",
        str(tmp_path / "result.json"),
    ]
    index = values.index(missing)
    del values[index : index + 2]

    with arguments(values), pytest.raises(SystemExit):
        result_cli_main()


def test_result_cli_rejects_an_unknown_status(tmp_path: Path) -> None:
    """Restrict serialized statuses to the shared JobStatus domain."""
    with (
        arguments(
            [
                "result-cli",
                "--check-id",
                "build",
                "--title",
                "Build",
                "--status",
                "unknown",
                "--output",
                str(tmp_path / "result.json"),
            ]
        ),
        pytest.raises(SystemExit),
    ):
        result_cli_main()


def test_result_cli_reads_summary_file_and_multiple_metrics(tmp_path: Path) -> None:
    """Prefer a summary file and preserve every ordered metric."""
    source = tmp_path / "source.md"
    output = tmp_path / "result.json"
    source.write_text("Detailed report.\n")
    with arguments(
        [
            "result-cli",
            "--check-id",
            "coverage",
            "--title",
            "Coverage",
            "--status",
            "passed",
            "--summary",
            str(source),
            "--message",
            "ignored",
            "--metric",
            "Lines=99%",
            "--metric",
            "Branches=98%",
            "--output",
            str(output),
        ]
    ):
        assert result_cli_main() == 0

    assert read_job_result(output) == JobResult(
        "coverage",
        "Coverage",
        JobStatus.PASSED,
        "Detailed report.\n",
        (Metric("Lines", "99%"), Metric("Branches", "98%")),
    )


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

    assert read_job_result(output) == JobResult(
        "lint",
        "Lint",
        JobStatus.FAILED,
        "Detected source diagnostics: **1**\n\n"
        "<details><summary>Command output</summary>\n\n"
        "````text\nexample.py:3:2: invalid type\n````\n\n</details>",
        (Metric("Exit code", "1"), Metric("Diagnostics", "1")),
        (
            SourceAnnotation(
                "example.py",
                3,
                3,
                "invalid type",
                start_column=2,
                end_column=2,
            ),
        ),
    )
    assert summary.read_text() == (
        '<a id="quality-graph-lint"></a>\n\n'
        "## ❌ Lint\n\n"
        "| Metric | Value |\n"
        "| --- | ---: |\n"
        "| Exit code | 1 |\n"
        "| Diagnostics | 1 |\n\n"
        "Detected source diagnostics: **1**\n\n"
        "<details><summary>Command output</summary>\n\n"
        "````text\nexample.py:3:2: invalid type\n````\n\n</details>\n"
    )
    assert capsys.readouterr().err == (
        "::error file=example.py,line=3,endLine=3,col=2,endColumn=2::invalid type\n"
    )


@pytest.mark.parametrize(
    "missing",
    ["--check-id", "--title", "--exit-code", "--log", "--output", "--summary"],
)
def test_job_report_cli_requires_its_public_contract(tmp_path: Path, missing: str) -> None:
    """Reject invocations missing any required report input or destination."""
    log = tmp_path / "lint.log"
    log.write_text("clean\n")
    values = [
        "job-report",
        "--check-id",
        "lint",
        "--title",
        "Lint",
        "--exit-code",
        "0",
        "--log",
        str(log),
        "--output",
        str(tmp_path / "result.json"),
        "--summary",
        str(tmp_path / "summary.md"),
    ]
    index = values.index(missing)
    del values[index : index + 2]

    with arguments(values), pytest.raises(SystemExit):
        job_report_main()
