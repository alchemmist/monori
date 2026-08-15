"""Test conversion of tool diagnostics into source annotations."""

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
