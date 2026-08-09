"""Apply administrator approvals to a frontend bundle-size report."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast, override

from monori.ci.quality_graph.base import (
    ApprovalLifecycle,
    CheckExecution,
    QualityCheck,
    QualityRuntime,
    ReportCheckRequest,
    run_report_check,
)
from monori.ci.quality_graph.job_results import JobStatus, without_admin_controls
from monori.ci.quality_graph.models import CheckContext, CheckResult, Metric, Verdict
from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.reporting import (
    RenderedCheckReport,
    ReportFinding,
    ReportModel,
    ReportStatus,
    admin_commands,
    render_report,
)
from monori.common import JsonValue, array_value, number_value, object_value, string_value

STATUS_LABEL = "monori-bundle-size-failed"
STATE_RE = re.compile(r"<!-- monori-bundle-size-approvals: ([a-z0-9,-]*) -->")
PENDING_RE = re.compile(r"<!-- monori-bundle-size-pending: (\d+)(?: ([A-Za-z0-9_-]+))? -->")
APPROVALS = ApprovalLifecycle(
    "bundle",
    "bundle-",
    STATE_RE,
    "<!-- monori-bundle-size-approvals: {ids} -->",
    PENDING_RE,
    allow_file_commands=False,
    finding_ids_include_prefix=True,
)


@dataclass(frozen=True)
class BundleFinding:
    """Represent one critical bundle-size metric as an approvable finding."""

    finding_id: str
    path: str = ""


class BundleSizeCheck(QualityCheck[BundleFinding]):
    """Collect bundle-size findings and use the shared approval lifecycle."""

    definition = WORKFLOW_JOB_BY_ID["bundle-size"]
    approval_lifecycle = APPROVALS
    pending_marker: ClassVar[str | None] = "monori-bundle-size-pending"
    failure_label: ClassVar[str | None] = STATUS_LABEL

    @override
    def collect(self, context: CheckContext) -> CheckResult[BundleFinding]:
        """Parse the bundle report and return critical metric findings."""
        report = object_value(cast("JsonValue", json.loads(context.files["report"])), "report")
        entries = array_value(report.get("entries"), "entries")
        findings = tuple(
            BundleFinding(string_value(object_value(entry, "entry").get("id"), "finding id"))
            for entry in entries
            if object_value(entry, "entry").get("tier") == "critical"
        )
        return CheckResult(findings, Verdict.FAIL if findings else Verdict.PASS)


def append_commands(
    summary: str, entries: list[dict[str, JsonValue]], approved: set[str]
) -> RenderedCheckReport:
    """Render bundle details and commands through the shared report template."""
    finding_ids = {
        string_value(entry.get("id"), "finding id")
        for entry in entries
        if entry.get("tier") == "critical"
    }
    active_ids = finding_ids - approved
    failed = bool(active_ids)
    return render_report(
        ReportModel(
            "bundle-size",
            ReportStatus.FAILED if failed else ReportStatus.PASSED,
            content=summary.rstrip(),
            findings=tuple(
                ReportFinding(
                    f"`{string_value(entry.get('label'), 'finding label')}` · "
                    f"`{string_value(entry.get('id'), 'finding id')}`",
                    string_value(entry.get("id"), "finding id") in approved,
                )
                for entry in entries
            ),
            admin=admin_commands("bundle", active_ids, finding_ids & approved),
        )
    )


def format_kib(value: JsonValue) -> str:
    """Format a numeric byte count as kibibytes or reject non-numeric JSON values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        message = "Expected numeric bundle size"
        raise TypeError(message)
    return f"{value / 1024:.1f} KiB"


def render_summary(report: dict[str, JsonValue]) -> str:
    """Render summary."""
    entries = [
        object_value(item, "entry") for item in array_value(report.get("entries"), "entries")
    ]
    lines = [
        "| Metric | Merge base | Pull request | Change | Tier |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for entry in entries:
        delta = int(number_value(entry.get("delta"), "delta"))
        percent = float(number_value(entry.get("percent"), "percent"))
        sign = "+" if delta > 0 else ""
        lines.append(
            f"| {string_value(entry.get('label'), 'finding label')} | "
            f"{format_kib(entry.get('base'))} | "
            f"{format_kib(entry.get('current'))} | "
            f"{sign}{format_kib(delta)} ({sign}{percent:.2f}%) | "
            f"{string_value(entry.get('tier'), 'tier')} |"
        )
    growth = [
        object_value(item, "asset growth")
        for item in array_value(report.get("assetGrowth"), "asset growth")
    ]
    lines.extend(["", "<details><summary>Largest asset increases</summary>", ""])
    if growth:
        lines.extend(
            [
                f"- `{string_value(item.get('asset'), 'asset')}`: "
                f"+{format_kib(item.get('delta'))} gzip"
                for item in growth
            ]
        )
    else:
        lines.append("No individual asset increased after normalizing build hashes.")
    lines.extend(["", "</details>"])
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class BundleExecutionContext:
    """Carry parsed bundle report data into shared lifecycle publication."""

    report_path: Path
    summary_path: Path
    report: dict[str, JsonValue]
    entries: list[dict[str, JsonValue]]
    finding_ids: set[str]


def build_execution(context: BundleExecutionContext, approved: set[str]) -> CheckExecution:
    """Build the bundle result after the shared lifecycle resolves approvals."""
    failed = context.report.get("verdict") == "critical" and context.finding_ids != approved
    context.report["approvedFindings"] = cast("JsonValue", sorted(approved))
    context.report["verdict"] = "critical" if failed else "none"
    context.report_path.write_text(json.dumps(context.report, indent=2, sort_keys=True) + "\n")
    rendered = append_commands(render_summary(context.report), context.entries, approved)
    summary = without_admin_controls(rendered.summary)
    context.summary_path.write_text(summary)
    return CheckExecution(
        JobStatus.FAILED if failed else JobStatus.PASSED,
        summary,
        (
            Metric("Regressions", str(len(context.finding_ids))),
            Metric("Active", str(len(context.finding_ids - approved))),
        ),
        rendered.controls,
        rendered.control_notes,
    )


def main() -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    runtime = QualityRuntime.from_environment()
    report_path = Path(os.environ["REPORT_PATH"])
    report = object_value(cast("JsonValue", json.loads(report_path.read_text())), "report")
    check = BundleSizeCheck()
    result = check.collect(CheckContext({"report": report_path.read_text()}, {}))
    entries = [
        object_value(item, "entry") for item in array_value(report.get("entries"), "entries")
    ]
    number = int(number_value(report.get("prNumber"), "pull request number"))
    ids = {finding.finding_id for finding in result.findings}
    summary_path = Path(os.environ["SUMMARY_PATH"])
    context = BundleExecutionContext(report_path, summary_path, report, entries, ids)
    request = ReportCheckRequest(
        runtime.github,
        number,
        result.findings,
        runtime.publisher,
        runtime.read_only,
    )
    return run_report_check(check, request, lambda approved: build_execution(context, approved))


if __name__ == "__main__":
    raise SystemExit(main())
