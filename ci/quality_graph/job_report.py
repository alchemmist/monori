"""Convert one make-command execution into a portable Quality Graph result."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from monori.ci.quality_graph.job_results import (
    AnnotationLevel,
    JobMetric,
    JobResult,
    JobStatus,
    SourceAnnotation,
    append_job_summary,
    grouped_annotations,
    workflow_annotation_command,
    write_job_result,
)

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
COLON_DIAGNOSTIC_RE = re.compile(
    r"^(?P<path>[^:\n]+\.(?:py|pyi|ts|tsx|js|jsx|css|html|sql|ya?ml|md|toml|jsonc?))"
    r":(?P<line>\d+)(?::(?P<column>\d+))?"
    r"(?::|\s+-)\s*(?P<message>.+)$"
)
PAREN_DIAGNOSTIC_RE = re.compile(
    r"^(?P<path>[^()\n]+\.(?:ts|tsx|js|jsx))"
    r"\((?P<line>\d+),(?P<column>\d+)\):\s*(?P<message>.+)$"
)
PYTEST_FAILURE_RE = re.compile(r"^(?P<path>[^:\n]+\.py):(?P<line>\d+):\s+(?P<message>.+)$")
MAX_SUMMARY_LOG_CHARACTERS = 200_000


def parse_diagnostics(log: str) -> tuple[SourceAnnotation, ...]:
    """Extract trustworthy source locations from common project tool output."""
    annotations: list[SourceAnnotation] = []
    for raw_line in ANSI_RE.sub("", log).splitlines():
        line = raw_line.strip()
        match = (
            COLON_DIAGNOSTIC_RE.match(line)
            or PAREN_DIAGNOSTIC_RE.match(line)
            or PYTEST_FAILURE_RE.match(line)
        )
        if match is None:
            continue
        path = match.group("path")
        source_line = int(match.group("line"))
        raw_column = match.groupdict().get("column")
        column = int(raw_column) if raw_column is not None else None
        message = match.group("message").strip()
        annotations.append(
            SourceAnnotation(
                path,
                source_line,
                source_line,
                message,
                AnnotationLevel.FAILURE,
                start_column=column,
                end_column=column,
            )
        )
    return tuple(dict.fromkeys(annotations))


def diagnostic_summary(log: str, annotation_count: int) -> str:
    """Render bounded diagnostic output without allowing Markdown fence injection."""
    clean = ANSI_RE.sub("", log).strip()
    if not clean:
        return "No diagnostic output was produced."
    omitted = max(0, len(clean) - MAX_SUMMARY_LOG_CHARACTERS)
    clean = clean[:MAX_SUMMARY_LOG_CHARACTERS]
    fence = "`" * (max((len(match.group()) for match in re.finditer(r"`+", clean)), default=2) + 1)
    notice = (
        f"\n\n_Output truncated; {omitted} characters remain available in the job log._"
        if omitted
        else ""
    )
    return (
        f"Detected source diagnostics: **{annotation_count}**\n\n"
        f"<details><summary>Command output</summary>\n\n{fence}text\n{clean}\n{fence}"
        f"{notice}\n\n</details>"
    )


def build_result(check_id: str, title: str, exit_code: int, log: str) -> JobResult:
    """Build one job result from a completed make invocation."""
    annotations = parse_diagnostics(log)
    status = JobStatus.PASSED if exit_code == 0 else JobStatus.FAILED
    return JobResult(
        check_id,
        title,
        status,
        diagnostic_summary(log, len(annotations)),
        (JobMetric("Exit code", str(exit_code)), JobMetric("Diagnostics", str(len(annotations)))),
        annotations,
    )


def main() -> int:
    """Render a make-command log into summary, annotations, and JSON output."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    result = build_result(args.check_id, args.title, args.exit_code, args.log.read_text())
    write_job_result(args.output, result)
    append_job_summary(args.summary, result)
    for annotation in grouped_annotations(result.annotations):
        sys.stderr.write(f"{workflow_annotation_command(annotation)}\n")
    if len(result.annotations) > len(grouped_annotations(result.annotations)):
        sys.stderr.write(
            "::notice::Additional source diagnostics are available in the Job Summary.\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
