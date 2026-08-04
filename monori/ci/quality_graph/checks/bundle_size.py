"""Apply administrator approvals to a frontend bundle-size report."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import cast

import httpx

from monori.ci.lib.github import HTTP_NO_CONTENT, HTTP_NOT_FOUND, REQUEST_TIMEOUT_SECONDS
from monori.ci.quality_graph.commands import (
    QualityGraphCommand,
    decode_command,
    parse_command,
    validate_command,
)
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


def json_number(value: JsonValue, context: str) -> int | float:
    """Return a numeric JSON bundle-size value."""
    return number_value(value, context)


def state_from_body(body: str) -> set[str]:
    """State from body for this module."""
    match = STATE_RE.search(body)
    return set(match.group(1).split(",")) if match and match.group(1) else set()


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


class GitHub:
    """Minimal GitHub API client for bundle-size approvals and labels."""

    def __init__(self) -> None:
        """Initialize bundle-size gate GitHub client with environment credentials."""
        self.base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repo = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Send GitHub API request and return parsed JSON response."""
        data = None if payload is None else json.dumps(payload).encode()
        try:
            response = httpx.request(
                method,
                f"{self.base}/repos/{self.repo}{path}",
                content=data,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                },
            )
        except httpx.RequestError as error:
            message = f"GitHub API {method} {path} failed: {error}"
            raise RuntimeError(message) from error
        if response.status_code == HTTP_NO_CONTENT:
            return None
        if response.status_code == HTTP_NOT_FOUND and method in {"GET", "DELETE"}:
            return None
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            message = f"GitHub API {method} {path} failed: HTTP {response.status_code}"
            raise RuntimeError(message) from error
        return cast("JsonValue", response.json())

    def sync_label(self, number: int, *, failed: bool) -> None:
        """Sync failure label state on issue based on check result."""
        encoded = urllib.parse.quote(STATUS_LABEL, safe="")
        if failed:
            if self.request("GET", f"/labels/{encoded}") is None:
                self.request("POST", "/labels", {"name": STATUS_LABEL, "color": "b60205"})
            self.request("POST", f"/issues/{number}/labels", {"labels": [STATUS_LABEL]})
        else:
            self.request("DELETE", f"/issues/{number}/labels/{encoded}")


def command_from_pending(github: GitHub, body: str) -> QualityGraphCommand | None:
    """Command from pending for this module."""
    match = PENDING_RE.search(body)
    if not match:
        return None
    if match.group(2):
        return decode_command(match.group(2))
    comment = object_value(github.request("GET", f"/issues/comments/{match.group(1)}"), "comment")
    command = parse_command(string_value(comment.get("body"), "comment body").strip())
    if command and validate_command(command) is not None:
        command = None
    user = object_value(comment.get("user", {}), "comment user")
    login = string_value(user.get("login"), "comment login")
    permission = object_value(
        github.request("GET", f"/collaborators/{urllib.parse.quote(login, safe='')}/permission"),
        "permission",
    )
    return command if permission.get("permission") == "admin" else None


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
    """Format kib for this module."""
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
    approved = state_from_body(body) & ids
    command = command_from_pending(github, body)
    approved = apply_command(command, ids, approved)
    if command:
        body = PENDING_RE.sub("", body).rstrip()
        marker = f"<!-- monori-bundle-size-approvals: {','.join(sorted(approved))} -->"
        body = (
            STATE_RE.sub(marker, body) if STATE_RE.search(body) else f"{body}\n\n{marker}".strip()
        )
        github.request("PATCH", f"/pulls/{number}", {"body": body})
    failed = report.get("verdict") == "critical" and ids != approved
    report["approvedFindings"] = cast("JsonValue", sorted(approved))
    report["verdict"] = "critical" if failed else "none"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    summary_path = Path(os.environ["SUMMARY_PATH"])
    summary_path.write_text(append_commands(render_summary(report), entries, approved))
    github.sync_label(number, failed=failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
