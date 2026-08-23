"""Publish time-bomb warnings through the shared Quality Graph job lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from monori.ci.lib.diagnostics import parse_diagnostics, parse_diff_annotations
from monori.ci.quality_graph.job_results import JobResult, JobStatus
from monori.ci.quality_graph.models import Metric
from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.run_job import CommandResult, MakeCheck

if TYPE_CHECKING:
    from monori.ci.quality_graph.registry import WorkflowJobDefinition


@dataclass(frozen=True)
class TimeBombResultAdapter:
    """Convert non-blocking timestamp diagnostics into a warning result."""

    def build(
        self,
        definition: WorkflowJobDefinition,
        command: CommandResult,
        diff: str,
    ) -> JobResult:
        """Build a warning result while preserving a successful command exit code."""
        annotations = (*parse_diagnostics(command.output), *parse_diff_annotations(diff))
        status = JobStatus.WARNING if annotations else JobStatus.PASSED
        if annotations:
            lines = "\n".join(
                f"- `{annotation.path}:{annotation.start_line}` — {annotation.message}"
                for annotation in annotations
            )
            summary = (
                "Raw timestamp literals can become timezone- or clock-sensitive time bombs. "
                "Prefer the project time helpers or derive the value at runtime.\n\n"
                f"<details><summary>Warnings ({len(annotations)})</summary>\n\n"
                f"{lines}\n\n</details>"
            )
        else:
            summary = "No plausible Unix timestamp literals were added."
        return JobResult(
            definition.job_id,
            definition.title,
            status,
            summary,
            (Metric("Warnings", str(len(annotations))),),
            annotations,
        )


TIME_BOMB_RESULT_ADAPTER = TimeBombResultAdapter()
CHECK = MakeCheck(
    WORKFLOW_JOB_BY_ID["time-bombs"],
    "time-bombs",
    result_adapter=TIME_BOMB_RESULT_ADAPTER,
)


def main() -> int:
    """Run the local detector and publish its portable Quality Graph result."""
    return CHECK.main()


if __name__ == "__main__":
    raise SystemExit(main())
