"""Apply administrator approvals to a frontend performance report."""

import hashlib
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
STATE_RE = re.compile(r"<!-- monori-frontend-performance-approvals: ([0-9a-f,]*) -->")
PENDING_RE = re.compile(
    r"<!-- monori-frontend-performance-pending: (\d+)(?: ([A-Za-z0-9_-]+))? -->"
)


def finding_id(entry: dict[str, JsonValue]) -> str:
    """Build deterministic finding id for a performance entry."""
    route = string_value(entry.get("route_id"), "entry route id")
    metric = string_value(entry.get("metric_id"), "entry metric id")
    digest = hashlib.sha256(f"{route}:{metric}".encode()).hexdigest()[:12]
    return f"{FINDING_ID_PREFIX}{digest}"


class GitHub:
    """Minimal GitHub API client for performance check commands."""

    def __init__(self) -> None:
        """Initialize frontend performance gate GitHub client from env."""
        self.base_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repository = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Send GitHub API request and return parsed JSON response."""
        url = f"{self.base_url}/repos/{self.repository}{path}"
        data = None if payload is None else json.dumps(payload).encode()
        try:
            response = httpx.request(
                method,
                url,
                content=data,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "Content-Type": "application/json",
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

    def ensure_label(self, name: str) -> None:
        """Create label if needed and ensure it exists in repository."""
        encoded = urllib.parse.quote(name, safe="")
        if self.request("GET", f"/labels/{encoded}") is None:
            self.request(
                "POST",
                "/labels",
                {
                    "name": name,
                    "color": "b60205",
                    "description": "Frontend performance gate state",
                },
            )


def is_admin(github: GitHub, login: str) -> bool:
    """Return whether admin."""
    encoded = urllib.parse.quote(login, safe="")
    permission = github.request("GET", f"/collaborators/{encoded}/permission")
    return (
        permission is not None
        and object_value(permission, "permission").get("permission") == "admin"
    )


def state_from_body(body: str) -> set[str]:
    """State from body for this module."""
    match = STATE_RE.search(body)
    return set(match.group(1).split(",")) if match and match.group(1) else set()


def update_body_state(github: GitHub, number: int, body: str, approved: set[str]) -> str:
    """Update body state."""
    marker = f"<!-- monori-frontend-performance-approvals: {','.join(sorted(approved))} -->"
    updated = STATE_RE.sub(marker, body)
    if updated == body:
        updated = f"{body.rstrip()}\n\n{marker}" if body.strip() else marker
    if updated != body:
        github.request("PATCH", f"/pulls/{number}", {"body": updated})
    return updated


def command_from_pending(github: GitHub, body: str) -> QualityGraphCommand | None:
    """Command from pending for this module."""
    match = PENDING_RE.search(body)
    if not match:
        return None
    if match.group(2):
        return decode_command(match.group(2))
    comment = object_value(github.request("GET", f"/issues/comments/{match.group(1)}"), "comment")
    command = parse_command((optional_string(comment.get("body")) or "").strip())
    if command and validate_command(command) is not None:
        command = None
    author = object_value(comment.get("user", {}), "comment user")
    login = optional_string(author.get("login"))
    return command if command and login and is_admin(github, login) else None


def entry_ids(entries: list[dict[str, JsonValue]]) -> set[str]:
    """Entry ids for this module."""
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
    approved = state_from_body(body) & entry_ids(entries)
    command = command_from_pending(github, body)
    approved = apply_command(command, entries, approved)
    if command is not None:
        body = PENDING_RE.sub("", body).rstrip()
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
    if failed:
        github.ensure_label(STATUS_LABEL)
        github.request("POST", f"/issues/{number}/labels", {"labels": [STATUS_LABEL]})
    else:
        github.request(
            "DELETE",
            f"/issues/{number}/labels/{urllib.parse.quote(STATUS_LABEL, safe='')}",
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
