"""Test workflow annotation publication."""

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


def test_annotation_publisher_groups_limits_and_reports_omissions() -> None:
    """Publish workflow commands through the single annotation boundary."""
    stream = StringIO()
    annotations = [
        SourceAnnotation("same.py", 1, 1, "first"),
        SourceAnnotation("same.py", 1, 1, "second"),
        *(SourceAnnotation(f"file-{index}.py", 1, 1, "failure") for index in range(20)),
    ]

    publish_workflow_annotations(
        annotations,
        omitted_message="More findings are in the summary.",
        stream=stream,
    )

    output = stream.getvalue()
    assert output.count("::error ") == MAX_STEP_ANNOTATIONS
    assert "first%0Asecond" in output
    assert "::notice::More findings are in the summary." in output


def test_control_markers_restore_reversible_checkbox_state() -> None:
    """Recover both commands from a rendered administrator checkbox."""
    control = JobControl(
        "/qg ignore suppression-a",
        "/qg remove-ignore suppression-a",
        checked=True,
    )
    body = f"- [x] `{control.command}` <!-- {control.marker} -->"

    assert controls_from_markdown(body) == (control,)


def test_workflow_command_escapes_untrusted_annotation_data() -> None:
    """Prevent source diagnostics from breaking GitHub workflow command syntax."""
    rendered = workflow_annotation_command(
        SourceAnnotation("a,b.py", 1, 1, "line one\nline two", title="bad:title")
    )

    assert rendered == (
        "::error file=a%2Cb.py,line=1,endLine=1,title=bad%3Atitle::line one%0Aline two"
    )
    assert escape_data("100%\r\nnext") == "100%25%0D%0Anext"
