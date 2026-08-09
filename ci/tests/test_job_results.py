"""Test portable Quality Graph job results."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest

from monori.ci.lib.annotations import (
    MAX_STEP_ANNOTATIONS,
    AnnotationLevel,
    SourceAnnotation,
    escape_data,
    grouped_annotations,
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
    JobMetric,
    JobResult,
    JobResultPublisher,
    JobStatus,
    append_job_summary,
    controls_from_markdown,
    read_job_result,
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
    assert path.read_text() == (
        "{\n"
        '  "annotations": [\n'
        "    {\n"
        '      "endColumn": null,\n'
        '      "endLine": 2,\n'
        '      "level": "failure",\n'
        '      "message": "broken",\n'
        '      "path": "example.py",\n'
        '      "startColumn": null,\n'
        '      "startLine": 2,\n'
        '      "title": null\n'
        "    }\n"
        "  ],\n"
        '  "checkId": "lint",\n'
        '  "controlNotes": [],\n'
        '  "controls": [\n'
        "    {\n"
        '      "checked": false,\n'
        '      "command": "/qg ignore object-a",\n'
        '      "reverseCommand": "/qg remove-ignore object-a"\n'
        "    }\n"
        "  ],\n"
        '  "metrics": [],\n'
        '  "status": "failed",\n'
        '  "summary": "Complete diagnostics",\n'
        '  "title": "Lint"\n'
        "}\n"
    )


def test_grouped_annotations_merge_one_location_and_apply_limit() -> None:
    """Avoid noisy repeated annotations while retaining every source location."""
    annotations = [
        SourceAnnotation("same.py", 1, 1, "first"),
        SourceAnnotation("same.py", 1, 1, "second"),
        *(SourceAnnotation(f"file-{index}.py", 1, 1, "failure") for index in range(20)),
    ]

    grouped = grouped_annotations(annotations)

    assert len(grouped) == MAX_STEP_ANNOTATIONS
    assert grouped[0].message == "first\nsecond"


def test_grouped_annotations_preserve_distinct_titles() -> None:
    """Keep diagnostics from different rules separate at one source range."""
    grouped = grouped_annotations(
        (
            SourceAnnotation("same.py", 1, 1, "first", title="rule-a"),
            SourceAnnotation("same.py", 1, 1, "second", title="rule-b"),
        )
    )

    assert [(item.title, item.message) for item in grouped] == [
        ("rule-a", "first"),
        ("rule-b", "second"),
    ]


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


def test_warning_diagnostic_keeps_warning_annotation_level() -> None:
    """Avoid presenting an explicit tool warning as an error annotation."""
    annotations = parse_diagnostics("server/app.py:4:7: warning: deprecated call")

    assert annotations[0].level is AnnotationLevel.WARNING


def test_playwright_results_do_not_become_source_annotations() -> None:
    """Keep Playwright list-reporter results out of GitHub source annotations."""
    annotations = parse_diagnostics(
        "\u2713  10 [chromium] \u203a e2e/dashboard.spec.ts:3:1 \u203a dashboard shows the "
        "seeded balances\n"
        "\u2718   2 [chromium] \u203a e2e/auth.spec.ts:20:1 \u203a signing in through the login "
        "page\n"
    )

    assert annotations == ()


def test_multiline_tool_diagnostics_become_source_annotations() -> None:
    """Parse ESLint, SQLFluff, Bandit, and Semgrep output through one library API."""
    annotations = parse_diagnostics(
        """/home/runner/work/monori/monori/web/src/app.tsx
  28:15  error  Unsafe assignment  @typescript-eslint/no-unsafe-assignment
== [server/query.sql] FAIL
L:  12 | P:   4 | LT01 | Unexpected whitespace.
>> Issue: [B101:assert_used] Use of assert detected.
Location: server/app/service.py:42:5
ci/quality_graph/base.py
\u276f\u2771 python.security.example
171┆ dangerous_call()
"""
    )

    assert [(item.path, item.start_line, item.start_column) for item in annotations] == [
        ("web/src/app.tsx", 28, 15),
        ("server/query.sql", 12, 4),
        ("server/app/service.py", 42, 5),
        ("ci/quality_graph/base.py", 171, None),
    ]
    assert annotations[1].title == "LT01"
    assert annotations[2].message.startswith("[B101:assert_used]")
    assert annotations[3].message == "python.security.example"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("/runner/project/common/json.py", "common/json.py"),
        ("/runner/project/ci/lib/github.py", "ci/lib/github.py"),
        ("/runner/project/server/app/main.py", "server/app/main.py"),
        ("/runner/project/web/src/main.tsx", "web/src/main.tsx"),
        ("./relative.py", "relative.py"),
        ("already/relative.py", "already/relative.py"),
    ],
)
def test_diagnostic_paths_are_normalized(source: str, expected: str) -> None:
    """Normalize every supported workspace root without changing relative paths."""
    assert normalize_source_path(source) == expected


def test_context_parser_preserves_state_and_fallback_messages() -> None:
    """Carry file and issue context across multiline diagnostic formats."""
    context, annotation, handled = parse_context_line(
        "/runner/project/server/app/main.py",
        DiagnosticContext(message="saved issue"),
    )
    assert (context, annotation, handled) == (
        DiagnosticContext("server/app/main.py", "saved issue"),
        None,
        True,
    )
    context, annotation, handled = parse_context_line(
        "17┆ dangerous_call()",
        DiagnosticContext("ci/example.py"),
    )
    assert (context, annotation, handled) == (
        DiagnosticContext("ci/example.py"),
        SourceAnnotation("ci/example.py", 17, 17, "Static analysis finding"),
        True,
    )
    assert parse_context_line("ordinary output", context) == (context, None, False)


def test_annotation_conversion_handles_warning_and_missing_column() -> None:
    """Derive severity and optional columns from a supported regex match."""
    match = COLON_RE.match("./example.py:4: warning: deprecated")
    assert match is not None
    assert annotation_from_match("./example.py", match, title="rule") == SourceAnnotation(
        "example.py",
        4,
        4,
        "warning: deprecated",
        AnnotationLevel.WARNING,
        title="rule",
    )


def test_formatter_diff_hunks_become_precise_source_annotations() -> None:
    """Annotate every changed range produced by an optional formatter fix target."""
    annotations = parse_diff_annotations(
        """diff --git a/web/src/app.tsx b/web/src/app.tsx
--- a/web/src/app.tsx
+++ b/web/src/app.tsx
@@ -4,2 +4,3 @@
-old
+new
+line
diff --git a/server/app.py b/server/app.py
--- a/server/app.py
+++ b/server/app.py
@@ -10 +10 @@
-old
+new
"""
    )

    assert [(item.path, item.start_line, item.end_line) for item in annotations] == [
        ("web/src/app.tsx", 4, 6),
        ("server/app.py", 10, 10),
    ]


def test_formatter_diff_ignores_deletions_and_requires_a_target_file() -> None:
    """Ignore deletion-only and orphaned hunks while defaulting an omitted count."""
    annotations = parse_diff_annotations(
        """@@ -1 +2 @@
+++ b/example.py
@@ -1 +7 @@
@@ -9 +10,0 @@
"""
    )

    assert annotations == (
        SourceAnnotation(
            "example.py",
            7,
            7,
            "This source range is not formatted.",
            title="Formatting",
        ),
    )


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


def test_workflow_command_escapes_untrusted_annotation_data() -> None:
    """Prevent source diagnostics from breaking GitHub workflow command syntax."""
    rendered = workflow_annotation_command(
        SourceAnnotation("a,b.py", 1, 1, "line one\nline two", title="bad:title")
    )

    assert rendered == (
        "::error file=a%2Cb.py,line=1,endLine=1,title=bad%3Atitle::line one%0Aline two"
    )
    assert escape_data("100%\r\nnext") == "100%25%0D%0Anext"


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
        (JobMetric("Findings", "0"),),
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
        (JobMetric("Score", "80%"),),
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
        (JobMetric("Lines", "99%"), JobMetric("Branches", "98%")),
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
        "```text\nexample.py:3:2: invalid type\n```\n\n</details>",
        (JobMetric("Exit code", "1"), JobMetric("Diagnostics", "1")),
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
        "```text\nexample.py:3:2: invalid type\n```\n\n</details>\n"
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
