"""Apply administrator approvals to a frontend performance report."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast, override

from monori.ci.lib.findings import stable_finding_id
from monori.ci.lib.github import GitHub
from monori.ci.quality_graph.base import (
    ApprovalLifecycle,
    CheckExecution,
    QualityCheck,
    ReportCheckRequest,
    run_report_check,
)
from monori.ci.quality_graph.job_results import (
    JobMetric,
    JobResultPublisher,
    JobStatus,
    without_admin_controls,
)
from monori.ci.quality_graph.models import CheckContext, CheckResult, Verdict
from monori.ci.quality_graph.reporting import (
    RenderedCheckReport,
    ReportFinding,
    ReportModel,
    ReportStatus,
    admin_commands,
    render_report,
)
from monori.common import (
    JsonValue,
    array_value,
    integer_value,
    object_value,
    string_value,
)

STATUS_LABEL = "monori-frontend-performance-failed"
FINDING_ID_PREFIX = "frontend-"
STATE_RE = re.compile(r"<!-- monori-frontend-performance-approvals: ([a-z0-9,-]*) -->")
PENDING_RE = re.compile(
    r"<!-- monori-frontend-performance-pending: (\d+)(?: ([A-Za-z0-9_-]+))? -->"
)
APPROVALS = ApprovalLifecycle(
    "frontend",
    FINDING_ID_PREFIX,
    STATE_RE,
    "<!-- monori-frontend-performance-approvals: {ids} -->",
    PENDING_RE,
    allow_file_commands=False,
    finding_ids_include_prefix=True,
)


@dataclass(frozen=True)
class FrontendPerformanceFinding:
    """Represent one regressed frontend metric as an approvable finding."""

    finding_id: str
    path: str = ""


class FrontendPerformanceCheck(QualityCheck[FrontendPerformanceFinding]):
    """Collect frontend regressions and use the shared approval lifecycle."""

    gate = "frontend"
    job_id = "frontend-performance"
    report_marker = "frontend-performance"
    approval_lifecycle = APPROVALS
    pending_marker: ClassVar[str | None] = "monori-frontend-performance-pending"
    failure_label: ClassVar[str | None] = STATUS_LABEL

    @override
    def collect(self, context: CheckContext) -> CheckResult[FrontendPerformanceFinding]:
        """Parse the performance report and return all regressed metric findings."""
        report = object_value(cast("JsonValue", json.loads(context.files["report"])), "report")
        entries = array_value(report.get("entries"), "entries")
        findings = tuple(
            FrontendPerformanceFinding(finding_id(object_value(entry, "report entry")))
            for entry in entries
            if object_value(entry, "report entry").get("tier") != "none"
        )
        return CheckResult(findings, Verdict.FAIL if findings else Verdict.PASS)


def finding_id(entry: dict[str, JsonValue]) -> str:
    """Build deterministic finding id for a performance entry."""
    route = string_value(entry.get("route_id"), "entry route id")
    metric = string_value(entry.get("metric_id"), "entry metric id")
    digest = stable_finding_id(f"{route}:{metric}")
    return f"{FINDING_ID_PREFIX}{digest}"


def entry_ids(entries: list[dict[str, JsonValue]]) -> set[str]:
    """Return finding IDs for measured entries that contain a regression."""
    return {finding_id(entry) for entry in entries if entry.get("tier") != "none"}


def append_commands(
    text: str,
    entries: list[dict[str, JsonValue]],
    approved: set[str],
    *,
    failed: bool,
) -> RenderedCheckReport:
    """Render performance details and commands through the shared template."""
    findings = [entry for entry in entries if entry.get("tier") != "none"]
    return render_report(
        ReportModel(
            "frontend-performance",
            ReportStatus.FAILED if failed else ReportStatus.PASSED,
            content=text.strip(),
            findings=tuple(
                ReportFinding(
                    f"`{string_value(entry.get('route_label'), 'route label')} · "
                    f"{string_value(entry.get('metric_label'), 'metric label')}` · "
                    f"`{finding_id(entry)}`",
                    finding_id(entry) in approved,
                )
                for entry in findings
            ),
            admin=admin_commands(
                "frontend",
                [
                    finding_id(entry)
                    for entry in findings
                    if entry.get("tier") != "none" and finding_id(entry) not in approved
                ],
                [finding_id(entry) for entry in findings if finding_id(entry) in approved],
            ),
        )
    )


@dataclass(frozen=True)
class FrontendExecutionContext:
    """Carry parsed performance report data into shared lifecycle publication."""

    report_path: Path
    summary_path: Path
    report: dict[str, JsonValue]
    entries: list[dict[str, JsonValue]]
    source_summary: str


def build_execution(context: FrontendExecutionContext, approved: set[str]) -> CheckExecution:
    """Build the performance result after shared lifecycle approval resolution."""
    original_verdict = string_value(context.report.get("verdict"), "verdict")
    active = {
        finding_id(entry)
        for entry in context.entries
        if entry.get("tier") in {"critical", "error"} and finding_id(entry) not in approved
    }
    failed = bool(active) or original_verdict == "error"
    context.report["verdict"] = original_verdict if failed else "none"
    context.report["commentRequired"] = failed
    context.report["approvedFindings"] = cast("JsonValue", sorted(approved))
    context.report_path.write_text(json.dumps(context.report, indent=2, sort_keys=True) + "\n")
    source_summary = re.sub(r"\A## .*\n*", "", context.source_summary, count=1)
    rendered = append_commands(source_summary, context.entries, approved, failed=failed)
    summary = without_admin_controls(rendered.summary)
    context.summary_path.write_text(summary)
    return CheckExecution(
        JobStatus.FAILED if failed else JobStatus.PASSED,
        summary,
        (
            JobMetric("Regressions", str(len(entry_ids(context.entries)))),
            JobMetric("Active", str(len(active))),
        ),
        rendered.controls,
        rendered.control_notes,
    )


def main() -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    github = GitHub()
    report_path = Path(os.environ["REPORT_PATH"])
    report = object_value(cast("JsonValue", json.loads(report_path.read_text())), "report")
    check = FrontendPerformanceCheck()
    result = check.collect(CheckContext({"report": report_path.read_text()}, {}))
    entries = [
        object_value(item, "report entry") for item in array_value(report.get("entries"), "entries")
    ]
    number = integer_value(report.get("prNumber"), "pull request number")
    read_only = os.environ.get("QUALITY_GRAPH_READ_ONLY", "").lower() == "true"
    summary_path = Path(os.environ["SUMMARY_PATH"])
    result_path = os.environ.get("QUALITY_RESULT_PATH")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    publisher = JobResultPublisher(
        Path(result_path) if result_path else None,
        Path(step_summary) if step_summary else None,
    )
    context = FrontendExecutionContext(
        report_path,
        summary_path,
        report,
        entries,
        summary_path.read_text(),
    )
    request = ReportCheckRequest(github, number, result.findings, publisher, read_only)
    return run_report_check(check, request, lambda approved: build_execution(context, approved))


if __name__ == "__main__":
    raise SystemExit(main())
