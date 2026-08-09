"""Apply administrator approvals to a frontend bundle-size report."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast, override

from monori.ci.lib.github import GitHub, sync_label
from monori.ci.quality_graph.base import ApprovalLifecycle, QualityCheck
from monori.ci.quality_graph.job_results import (
    JobMetric,
    JobResult,
    JobStatus,
    append_job_summary,
    controls_from_markdown,
    without_admin_controls,
    write_job_result,
)
from monori.ci.quality_graph.models import CheckContext, CheckResult, Verdict
from monori.ci.quality_graph.reporting import (
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

    gate = "bundle"
    job_id = "bundle-size"
    report_marker = "bundle-size"
    approval_lifecycle = APPROVALS
    pending_marker: ClassVar[str | None] = "monori-bundle-size-pending"

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


def append_commands(summary: str, entries: list[dict[str, JsonValue]], approved: set[str]) -> str:
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


def main() -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    github = GitHub()
    report_path = Path(os.environ["REPORT_PATH"])
    report = object_value(cast("JsonValue", json.loads(report_path.read_text())), "report")
    check = BundleSizeCheck()
    result = check.collect(CheckContext({"report": report_path.read_text()}, {}))
    entries = [
        object_value(item, "entry") for item in array_value(report.get("entries"), "entries")
    ]
    number = int(number_value(report.get("prNumber"), "pull request number"))
    pull = object_value(github.request("GET", f"/pulls/{number}"), "pull request")
    raw_body = pull.get("body")
    body = raw_body if isinstance(raw_body, str) else ""
    synced = check.sync_pending_approvals(github, number, body, result.findings)
    approved = synced.approved
    ids = {finding.finding_id for finding in result.findings}
    failed = report.get("verdict") == "critical" and ids != approved
    report["approvedFindings"] = cast("JsonValue", sorted(approved))
    report["verdict"] = "critical" if failed else "none"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    summary_path = Path(os.environ["SUMMARY_PATH"])
    rendered = append_commands(render_summary(report), entries, approved)
    summary = without_admin_controls(rendered)
    summary_path.write_text(summary)
    job_result = JobResult(
        check.job_id,
        "Frontend bundle size",
        JobStatus.FAILED if failed else JobStatus.PASSED,
        summary,
        (
            JobMetric("Regressions", str(len(ids))),
            JobMetric("Active", str(len(ids - approved))),
        ),
        controls=controls_from_markdown(rendered),
    )
    result_path = os.environ.get("QUALITY_RESULT_PATH")
    if result_path:
        write_job_result(Path(result_path), job_result)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        append_job_summary(Path(step_summary), job_result)
    sync_label(github, number, STATUS_LABEL, present=failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
