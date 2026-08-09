"""Publish a simple Quality Graph result from a composite action."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from monori.ci.quality_graph.job_results import (
    JobResult,
    JobResultPublisher,
    JobStatus,
)
from monori.ci.quality_graph.models import Metric

if TYPE_CHECKING:
    from monori.ci.quality_graph.registry import WorkflowJobDefinition


def publish_result_main(definition: WorkflowJobDefinition | None = None) -> int:
    """Write a typed result for an explicit or registered Quality Graph check."""
    parser = argparse.ArgumentParser()
    if definition is None:
        parser.add_argument("--check-id", required=True)
        parser.add_argument("--title", required=True)
    parser.add_argument("--status", choices=[status.value for status in JobStatus], required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--message", default="")
    parser.add_argument("--metric", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--job-summary", type=Path)
    args = parser.parse_args()
    check_id = args.check_id if definition is None else definition.job_id
    title = args.title if definition is None else definition.title
    metrics: list[Metric] = []
    for raw_metric in args.metric:
        label, separator, value = raw_metric.partition("=")
        if not separator:
            parser.error("--metric must use label=value")
        metrics.append(Metric(label, value))
    summary = args.summary.read_text() if args.summary is not None else args.message
    result = JobResult(
        check_id,
        title,
        JobStatus(args.status),
        summary,
        tuple(metrics),
    )
    JobResultPublisher(args.output, args.job_summary).publish(result)
    return 0


def main() -> int:
    """Publish a result whose identity is supplied by command-line arguments."""
    return publish_result_main()


if __name__ == "__main__":
    sys.exit(main())
