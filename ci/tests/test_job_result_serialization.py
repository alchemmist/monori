"""Test portable Quality Graph job-result serialization."""

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
