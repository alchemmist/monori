"""Convert one make-command execution into a portable Quality Graph result."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from monori.ci.lib.annotations import publish_workflow_annotations
from monori.ci.lib.diagnostics import ANSI_RE, parse_diagnostics, parse_diff_annotations
from monori.ci.quality_graph.job_results import (
    JobResult,
    JobResultPublisher,
    JobStatus,
)
from monori.ci.quality_graph.models import Metric

MAX_SUMMARY_LOG_CHARACTERS = 200_000


def diagnostic_summary(log: str, annotation_count: int) -> str:
    """Render bounded diagnostic output without allowing Markdown fence injection."""
    clean = ANSI_RE.sub("", log).strip()
    if not clean:
        return "No diagnostic output was produced."
    omitted = max(0, len(clean) - MAX_SUMMARY_LOG_CHARACTERS)
    clean = clean[:MAX_SUMMARY_LOG_CHARACTERS]
    max_backticks = max((len(match.group()) for match in re.finditer(r"`+", clean)), default=2)
    fence = "`" * max(4, max_backticks + 1)
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


def build_result(
    check_id: str,
    title: str,
    exit_code: int,
    log: str,
    diff: str = "",
) -> JobResult:
    """Build one job result from a completed make invocation."""
    annotations = tuple(dict.fromkeys((*parse_diagnostics(log), *parse_diff_annotations(diff))))
    status = JobStatus.PASSED if exit_code == 0 else JobStatus.FAILED
    return JobResult(
        check_id,
        title,
        status,
        diagnostic_summary(log, len(annotations)),
        (Metric("Exit code", str(exit_code)), Metric("Diagnostics", str(len(annotations)))),
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
    parser.add_argument("--diff", type=Path)
    args = parser.parse_args()
    diff = args.diff.read_text() if args.diff is not None and args.diff.exists() else ""
    result = build_result(args.check_id, args.title, args.exit_code, args.log.read_text(), diff)
    JobResultPublisher(args.output, args.summary).publish(result)
    publish_workflow_annotations(
        result.annotations,
        omitted_message="Additional source diagnostics are available in the Job Summary.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
