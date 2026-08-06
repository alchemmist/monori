"""Publish a simple Quality Graph result from a composite action."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from monori.ci.quality_graph.job_results import (
    JobMetric,
    JobResult,
    JobStatus,
    append_job_summary,
    write_job_result,
)


def main() -> int:
    """Write a typed result and append its detailed Job Summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--status", choices=[status.value for status in JobStatus], required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--message", default="")
    parser.add_argument("--metric", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metrics: list[JobMetric] = []
    for raw_metric in args.metric:
        label, separator, value = raw_metric.partition("=")
        if not separator:
            parser.error("--metric must use label=value")
        metrics.append(JobMetric(label, value))
    summary = args.summary.read_text() if args.summary is not None else args.message
    result = JobResult(
        args.check_id,
        args.title,
        JobStatus(args.status),
        summary,
        tuple(metrics),
    )
    write_job_result(args.output, result)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        append_job_summary(Path(summary_path), result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
