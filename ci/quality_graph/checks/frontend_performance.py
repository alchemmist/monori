"""Apply administrator approvals to a frontend performance report."""

from __future__ import annotations

import hashlib
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
from monori.common import (
    JsonValue,
    array_value,
    integer_value,
    object_value,
    optional_string,
    string_value,
)

if TYPE_CHECKING:
    from monori.ci.quality_graph.commands import QualityGraphCommand

STATUS_LABEL = "monori-frontend-performance-failed"
FINDING_ID_PREFIX = "frontend-"
STATE_RE = re.compile(r"<!-- monori-frontend-performance-approvals: ([0-9a-f,]*) -->")
PENDING_RE = re.compile(
    r"<!-- monori-frontend-performance-pending: (\d+)(?: ([A-Za-z0-9_-]+))? -->"
)
APPROVALS = ApprovalLifecycle(
    "frontend",
    FINDING_ID_PREFIX,
    STATE_RE,
    "<!-- monori-frontend-performance-approvals: {ids} -->",
    PENDING_RE,
)


def finding_id(entry: dict[str, JsonValue]) -> str:
    """Build deterministic finding id for a performance entry."""
    route = string_value(entry.get("route_id"), "entry route id")
    metric = string_value(entry.get("metric_id"), "entry metric id")
    digest = hashlib.sha256(f"{route}:{metric}".encode()).hexdigest()[:12]
    return f"{FINDING_ID_PREFIX}{digest}"


def update_body_state(github: GitHub, number: int, body: str, approved: set[str]) -> str:
    """Update body state."""
    return APPROVALS.persist_approvals(github, number, body, approved)


def entry_ids(entries: list[dict[str, JsonValue]]) -> set[str]:
    """Return finding IDs for measured entries that contain a regression."""
    return {finding_id(entry) for entry in entries if entry.get("tier") != "none"}


def apply_command(
    command: QualityGraphCommand | None,
    entries: list[dict[str, JsonValue]],
    approved: set[str],
) -> set[str]:
    """Apply command."""
    if command is None:
        return approved
    name = command.name
    arguments = command.arguments
    if name in {"help", "status", "ignore-file"}:
        return approved
    ids = entry_ids(entries)
    selected = (
        ids
        if name in {"ignore", "remove-ignore"} and "frontend" in arguments
        else {argument for argument in arguments if argument.startswith(FINDING_ID_PREFIX)}
    ) & ids
    return approved - selected if name == "remove-ignore" else approved | selected


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
            ReportStatus.FAIL if failed else ReportStatus.DONE,
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
    entries = [
        object_value(item, "report entry") for item in array_value(report.get("entries"), "entries")
    ]
    number = integer_value(report.get("prNumber"), "pull request number")
    pull = object_value(github.request("GET", f"/pulls/{number}"), "pull request")
    body = optional_string(pull.get("body")) or ""
    approved = APPROVALS.read(body) & entry_ids(entries)
    command = APPROVALS.pending_command(github, body)
    approved = apply_command(command, entries, approved)
    if command is not None:
        APPROVALS.consume_pending(github, body)
        body = APPROVALS.without_pending(body)
    if command is not None or STATE_RE.search(body):
        body = update_body_state(github, number, body, approved)

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
    summary_path.write_text(append_commands(summary, entries, approved, failed=failed))
    sync_label(github, number, STATUS_LABEL, present=failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
