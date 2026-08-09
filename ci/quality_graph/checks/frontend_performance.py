"""Apply administrator approvals to a frontend performance report."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast, override

from monori.ci.lib.findings import stable_finding_id
from monori.ci.lib.github import GitHub, sync_label
from monori.ci.quality_graph.base import ApprovalLifecycle, QualityCheck
from monori.ci.quality_graph.job_results import (
    JobMetric,
    JobResult,
    JobResultPublisher,
    JobStatus,
    controls_from_markdown,
    without_admin_controls,
)
from monori.ci.quality_graph.models import CheckContext, CheckResult, Verdict
from monori.ci.quality_graph.reporting import (
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
    optional_string,
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
) -> str:
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
    pull = object_value(github.request("GET", f"/pulls/{number}"), "pull request")
    body = optional_string(pull.get("body")) or ""
    synced = check.sync_pending_approvals(github, number, body, result.findings)
    approved = synced.approved

    original_verdict = string_value(report.get("verdict"), "verdict")
    active = {
        finding_id(entry)
        for entry in entries
        if entry.get("tier") in {"critical", "error"} and finding_id(entry) not in approved
    }
    failed = bool(active) or original_verdict == "error"
    effective_verdict = original_verdict if failed else "none"
    report["verdict"] = effective_verdict
    report["commentRequired"] = failed
    report["approvedFindings"] = cast("JsonValue", sorted(approved))
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    summary_path = Path(os.environ["SUMMARY_PATH"])
    summary = summary_path.read_text()
    summary = re.sub(r"\A## .*\n*", "", summary, count=1)
    rendered = append_commands(summary, entries, approved, failed=failed)
    summary = without_admin_controls(rendered)
    summary_path.write_text(summary)
    job_result = JobResult(
        check.job_id,
        "Frontend performance",
        JobStatus.FAILED if failed else JobStatus.PASSED,
        summary,
        (
            JobMetric("Regressions", str(len(entry_ids(entries)))),
            JobMetric("Active", str(len(active))),
        ),
        controls=controls_from_markdown(rendered),
    )
    result_path = os.environ.get("QUALITY_RESULT_PATH")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    JobResultPublisher(
        Path(result_path) if result_path else None,
        Path(step_summary) if step_summary else None,
    ).publish(job_result)
    sync_label(github, number, STATUS_LABEL, present=failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
