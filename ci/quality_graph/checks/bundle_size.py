"""Apply administrator approvals to a frontend bundle-size report."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import cast

import httpx

from ci.lib.github import HTTP_FORBIDDEN, HTTP_NO_CONTENT, HTTP_NOT_FOUND, REQUEST_TIMEOUT_SECONDS
from ci.quality_graph.commands import (
    QualityGraphCommand,
    admin_command_lines,
    parse_command,
    validate_command,
)

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

STATUS_LABEL = "monori-bundle-size-failed"
STATE_RE = re.compile(r"<!-- monori-bundle-size-approvals: ([a-z0-9,-]*) -->")
PENDING_RE = re.compile(r"<!-- monori-bundle-size-pending: (\d+) -->")


def obj(value: JsonValue, context: str) -> dict[str, JsonValue]:
    """Obj for this module."""
    if not isinstance(value, dict):
        message = f"Expected object for {context}"
        raise TypeError(message)
    return value


def string(value: JsonValue, context: str) -> str:
    """String for this module."""
    if not isinstance(value, str):
        message = f"Expected string for {context}"
        raise TypeError(message)
    return value


def json_number(value: JsonValue, context: str) -> int | float:
    """Json number for this module."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        message = f"Expected number for {context}"
        raise TypeError(message)
    return value


def array(value: JsonValue, context: str) -> list[JsonValue]:
    """Array for this module."""
    if not isinstance(value, list):
        message = f"Expected array for {context}"
        raise TypeError(message)
    return value


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
        if response.status_code == HTTP_FORBIDDEN and method in {"POST", "PATCH", "DELETE"}:
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
    comment = obj(github.request("GET", f"/issues/comments/{match.group(1)}"), "comment")
    command = parse_command(string(comment.get("body"), "comment body").strip())
    if command and validate_command(command) is not None:
        command = None
    user = obj(comment.get("user", {}), "comment user")
    login = string(user.get("login"), "comment login")
    permission = obj(
        github.request("GET", f"/collaborators/{urllib.parse.quote(login, safe='')}/permission"),
        "permission",
    )
    return command if permission.get("permission") == "admin" else None


def append_commands(summary: str, entries: list[dict[str, JsonValue]], approved: set[str]) -> str:
    """Append commands."""
    finding_ids = {
        string(entry.get("id"), "finding id")
        for entry in entries
        if entry.get("tier") == "critical"
    }
    active_ids = finding_ids - approved
    lines = ["", "<details><summary>For repository administrators</summary>", ""]
    lines.extend(admin_command_lines("bundle", active_ids, finding_ids & approved))
    lines.extend(["", "Findings:"])
    for entry in entries:
        finding = string(entry.get("id"), "finding id")
        marker = "✔" if finding in approved else "✗"
        lines.append(f"- {marker} `{string(entry.get('label'), 'finding label')}` · `{finding}`")
    return summary.rstrip() + "\n" + "\n".join(lines) + "\n\n</details>\n"


def format_kib(value: JsonValue) -> str:
    """Format kib for this module."""
    if not isinstance(value, (int, float)):
        message = "Expected numeric bundle size"
        raise TypeError(message)
    return f"{value / 1024:.1f} KiB"


def render_summary(report: dict[str, JsonValue], *, failed: bool) -> str:
    """Render summary."""
    entries = [obj(item, "entry") for item in array(report.get("entries"), "entries")]
    lines = [
        f"## {'❌' if failed else '✅'} Bundle size",
        "",
        "| Metric | Merge base | Pull request | Change | Tier |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for entry in entries:
        delta = int(json_number(entry.get("delta"), "delta"))
        percent = float(json_number(entry.get("percent"), "percent"))
        sign = "+" if delta > 0 else ""
        lines.append(
            f"| {string(entry.get('label'), 'finding label')} | "
            f"{format_kib(entry.get('base'))} | "
            f"{format_kib(entry.get('current'))} | "
            f"{sign}{format_kib(delta)} ({sign}{percent:.2f}%) | "
            f"{string(entry.get('tier'), 'tier')} |"
        )
    growth = [
        obj(item, "asset growth") for item in array(report.get("assetGrowth"), "asset growth")
    ]
    lines.extend(["", "<details><summary>Largest asset increases</summary>", ""])
    if growth:
        lines.extend(
            [
                f"- `{string(item.get('asset'), 'asset')}`: +{format_kib(item.get('delta'))} gzip"
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
    report = obj(cast("JsonValue", json.loads(report_path.read_text())), "report")
    entries = [obj(item, "entry") for item in array(report.get("entries"), "entries")]
    number = int(json_number(report.get("prNumber"), "pull request number"))
    pull = obj(github.request("GET", f"/pulls/{number}"), "pull request")
    raw_body = pull.get("body")
    body = raw_body if isinstance(raw_body, str) else ""
    ids = {
        string(entry.get("id"), "finding id")
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
    summary_path.write_text(
        append_commands(render_summary(report, failed=failed), entries, approved)
    )
    github.sync_label(number, failed=failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
