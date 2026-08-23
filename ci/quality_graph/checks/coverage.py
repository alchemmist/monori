"""Measure project test coverage."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from monori.ci.lib.annotations import SourceAnnotation
from monori.ci.lib.coverage_diff import (
    COVERAGE_REPORT_ADAPTER,
    CoverageReport,
    render_summary,
)
from monori.ci.quality_graph.job_results import JobResult, JobStatus
from monori.ci.quality_graph.models import Metric
from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID, WorkflowJobDefinition
from monori.ci.quality_graph.run_job import (
    DIAGNOSTIC_RESULT_ADAPTER,
    CommandResult,
    MakeCheck,
)


@dataclass(frozen=True)
class CoverageResultAdapter:
    """Convert the domain coverage report into the shared Quality Graph result."""

    report_path: Path

    def build(
        self,
        definition: WorkflowJobDefinition,
        command: CommandResult,
        diff: str,
    ) -> JobResult:
        """Publish typed coverage metrics, findings, and source annotations."""
        if not self.report_path.is_file():
            return self._invalid_report(
                definition, command, diff, "Coverage report was not produced"
            )
        try:
            payload = self.report_path.read_bytes()
        except OSError:
            return self._invalid_report(
                definition, command, diff, "Coverage report could not be read"
            )
        try:
            report = COVERAGE_REPORT_ADAPTER.validate_json(payload, strict=True)
        except ValidationError:
            return self._invalid_report(definition, command, diff, "Coverage report is invalid")
        return coverage_result(definition, report, command)

    @staticmethod
    def _invalid_report(
        definition: WorkflowJobDefinition,
        command: CommandResult,
        diff: str,
        message: str,
    ) -> JobResult:
        """Return a failed standard diagnostic result for unusable domain output."""
        output = f"{command.output.rstrip()}\n{message}\n"
        return DIAGNOSTIC_RESULT_ADAPTER.build(definition, CommandResult(1, output), diff)


def coverage_result(
    definition: WorkflowJobDefinition,
    report: CoverageReport,
    command: CommandResult,
) -> JobResult:
    """Map one validated coverage report onto the portable job-result protocol."""
    passed = command.returncode == 0 and report.passed
    touched = tuple(stack for stack in report.stacks if stack.touched)
    return JobResult(
        definition.job_id,
        definition.title,
        JobStatus.PASSED if passed else JobStatus.FAILED,
        render_summary(report, workflow_passed=command.returncode == 0),
        tuple(
            metric
            for stack in touched
            for metric in (
                Metric(f"{stack.name} total", f"{stack.total:.2f}%"),
                Metric(f"{stack.name} patch", f"{stack.patch:.2f}%"),
            )
        ),
        tuple(
            SourceAnnotation(
                finding.path,
                finding.start,
                finding.end,
                f"{finding.function}: changed lines are not covered",
                title="Coverage",
            )
            for stack in touched
            for finding in stack.findings
        ),
    )


CHECK = MakeCheck(
    WORKFLOW_JOB_BY_ID["coverage"],
    "coverage-diff",
    result_adapter=CoverageResultAdapter(Path("coverage-report/report.json")),
)


def main() -> int:
    """Collect coverage and publish its Quality Graph result."""
    return CHECK.main()


if __name__ == "__main__":
    raise SystemExit(main())
