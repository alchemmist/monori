"""Apply administrator approvals to a frontend bundle-size report."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, cast

from monori.ci.lib.github import GitHub, sync_label
from monori.ci.quality_graph.base import ApprovalLifecycle
from monori.ci.quality_graph.reporting import (
    ReportFinding,
    ReportModel,
    ReportStatus,
    admin_commands,
    render_report,
)
from monori.common import JsonValue, array_value, number_value, object_value, string_value

if TYPE_CHECKING:
    from monori.ci.quality_graph.commands import QualityGraphCommand

STATUS_LABEL = "monori-bundle-size-failed"
STATE_RE = re.compile(r"<!-- monori-bundle-size-approvals: ([a-z0-9,-]*) -->")
PENDING_RE = re.compile(r"<!-- monori-bundle-size-pending: (\d+)(?: ([A-Za-z0-9_-]+))? -->")
APPROVALS = ApprovalLifecycle(
    "bundle",
    "bundle-",
    STATE_RE,
    "<!-- monori-bundle-size-approvals: {ids} -->",
    PENDING_RE,
)


def json_number(value: JsonValue, context: str) -> int | float:
    """Return a numeric JSON bundle-size value."""
    return number_value(value, context)


def apply_command(
    command: QualityGraphCommand | None, ids: set[str], approved: set[str]
) -> set[str]:
    """Apply command."""
    if command is None:
        return approved
    name = command.name
    arguments = command.arguments
    if name in {"help", "status", "ignore-file"}:
        return approved
    if name == "ignore" and "bundle" in arguments:
        return approved | ids
    selected = (ids if name == "ignore" and "bundle" in arguments else set(arguments)) & ids
    return approved - selected if name == "remove-ignore" else approved | selected


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
            ReportStatus.FAIL if failed else ReportStatus.DONE,
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
        delta = int(json_number(entry.get("delta"), "delta"))
        percent = float(json_number(entry.get("percent"), "percent"))
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
    entries = [
        object_value(item, "entry") for item in array_value(report.get("entries"), "entries")
    ]
    number = int(json_number(report.get("prNumber"), "pull request number"))
    pull = object_value(github.request("GET", f"/pulls/{number}"), "pull request")
    raw_body = pull.get("body")
    body = raw_body if isinstance(raw_body, str) else ""
    ids = {
        string_value(entry.get("id"), "finding id")
        for entry in entries
        if entry.get("tier") == "critical"
    }
    approved = APPROVALS.read(body) & ids
    command = APPROVALS.pending_command(github, body)
    approved = apply_command(command, ids, approved)
    if command:
        APPROVALS.consume_pending(github, body)
        body = APPROVALS.without_pending(body)
        APPROVALS.write(github, number, body, approved)
    failed = report.get("verdict") == "critical" and ids != approved
    report["approvedFindings"] = cast("JsonValue", sorted(approved))
    report["verdict"] = "critical" if failed else "none"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    summary_path = Path(os.environ["SUMMARY_PATH"])
    summary_path.write_text(append_commands(render_summary(report), entries, approved))
    sync_label(github, number, STATUS_LABEL, present=failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
