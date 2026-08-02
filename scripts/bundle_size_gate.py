"""Apply administrator approvals to a frontend bundle-size report."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import cast

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

STATUS_LABEL = "monori-bundle-size-failed"
STATE_RE = re.compile(r"<!-- monori-bundle-size-approvals: ([a-z0-9,-]*) -->")
PENDING_RE = re.compile(r"<!-- monori-bundle-size-pending: (\d+) -->")
COMMAND_RE = re.compile(r"^/(ignore|ignore-all|remove-ignore)(?:\s+(\S+))?$")


def obj(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected object for {context}")
    return value


def string(value: JsonValue, context: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"Expected string for {context}")
    return value


def json_number(value: JsonValue, context: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"Expected number for {context}")
    return value


def array(value: JsonValue, context: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise RuntimeError(f"Expected array for {context}")
    return value


def parse_command(body: str) -> tuple[str, list[str] | None] | None:
    match = COMMAND_RE.fullmatch(body)
    if not match:
        return None
    name, argument = match.groups()
    if name == "ignore-all":
        return (name, None) if argument is None else None
    if not argument:
        return None
    arguments = [item.strip() for item in argument.split(",")]
    return (name, arguments) if all(arguments) else None


def state_from_body(body: str) -> set[str]:
    match = STATE_RE.search(body)
    return set(match.group(1).split(",")) if match and match.group(1) else set()


def apply_command(
    command: tuple[str, list[str] | None] | None, ids: set[str], approved: set[str]
) -> set[str]:
    if command is None:
        return approved
    name, arguments = command
    if name == "ignore-all":
        return approved | ids
    selected = set(arguments or []) & ids
    return approved - selected if name == "remove-ignore" else approved | selected


class GitHub:
    def __init__(self) -> None:
        self.base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repo = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{self.base}/repos/{self.repo}{path}",
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return None if response.status == 204 else cast(JsonValue, json.loads(response.read()))
        except urllib.error.HTTPError as error:
            if error.code == 404 and method in {"GET", "DELETE"}:
                return None
            raise RuntimeError(f"GitHub API {method} {path} failed: HTTP {error.code}") from error

    def sync_label(self, number: int, failed: bool) -> None:
        encoded = urllib.parse.quote(STATUS_LABEL, safe="")
        if failed:
            if self.request("GET", f"/labels/{encoded}") is None:
                self.request("POST", "/labels", {"name": STATUS_LABEL, "color": "b60205"})
            self.request("POST", f"/issues/{number}/labels", {"labels": [STATUS_LABEL]})
        else:
            self.request("DELETE", f"/issues/{number}/labels/{encoded}")


def command_from_pending(github: GitHub, body: str) -> tuple[str, list[str] | None] | None:
    match = PENDING_RE.search(body)
    if not match:
        return None
    comment = obj(github.request("GET", f"/issues/comments/{match.group(1)}"), "comment")
    command = parse_command(string(comment.get("body"), "comment body").strip())
    user = obj(comment.get("user", {}), "comment user")
    login = string(user.get("login"), "comment login")
    permission = obj(github.request("GET", f"/collaborators/{urllib.parse.quote(login, safe='')}/permission"), "permission")
    return command if permission.get("permission") == "admin" else None


def append_commands(summary: str, entries: list[dict[str, JsonValue]], approved: set[str]) -> str:
    lines = ["", "<details><summary>For repository administrators</summary>", "", "Post exactly one command as a new pull-request comment:", "", "- `/ignore bundle-<id>[,bundle-<id>...]`", "- `/ignore-all`", "- `/remove-ignore bundle-<id>[,bundle-<id>...]`", "", "Findings:"]
    for entry in entries:
        finding = string(entry.get("id"), "finding id")
        marker = "✔" if finding in approved else "✗"
        lines.append(f"- {marker} `{string(entry.get('label'), 'finding label')}` · `{finding}`")
    return summary.rstrip() + "\n" + "\n".join(lines) + "\n\n</details>\n"


def format_kib(value: JsonValue) -> str:
    if not isinstance(value, (int, float)):
        raise RuntimeError("Expected numeric bundle size")
    return f"{value / 1024:.1f} KiB"


def render_summary(report: dict[str, JsonValue], failed: bool) -> str:
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
            f"| {string(entry.get('label'), 'finding label')} | {format_kib(entry.get('base'))} | "
            f"{format_kib(entry.get('current'))} | {sign}{format_kib(delta)} ({sign}{percent:.2f}%) | "
            f"{string(entry.get('tier'), 'tier')} |"
        )
    growth = [obj(item, "asset growth") for item in array(report.get("assetGrowth"), "asset growth")]
    lines.extend(["", "<details><summary>Largest asset increases</summary>", ""])
    if growth:
        for item in growth:
            lines.append(
                f"- `{string(item.get('asset'), 'asset')}`: +{format_kib(item.get('delta'))} gzip"
            )
    else:
        lines.append("No individual asset increased after normalizing build hashes.")
    lines.extend(["", "</details>"])
    return "\n".join(lines) + "\n"


def main() -> int:
    github = GitHub()
    report_path = Path(os.environ["REPORT_PATH"])
    report = obj(cast(JsonValue, json.loads(report_path.read_text())), "report")
    entries = [obj(item, "entry") for item in array(report.get("entries"), "entries")]
    number = int(json_number(report.get("prNumber"), "pull request number"))
    pull = obj(github.request("GET", f"/pulls/{number}"), "pull request")
    raw_body = pull.get("body")
    body = raw_body if isinstance(raw_body, str) else ""
    ids = {string(entry.get("id"), "finding id") for entry in entries if entry.get("tier") == "critical"}
    approved = state_from_body(body) & ids
    command = command_from_pending(github, body)
    approved = apply_command(command, ids, approved)
    if command:
        body = PENDING_RE.sub("", body).rstrip()
        marker = f"<!-- monori-bundle-size-approvals: {','.join(sorted(approved))} -->"
        body = STATE_RE.sub(marker, body) if STATE_RE.search(body) else f"{body}\n\n{marker}".strip()
        github.request("PATCH", f"/pulls/{number}", {"body": body})
    failed = report.get("verdict") == "critical" and ids != approved
    report["approvedFindings"] = cast(JsonValue, sorted(approved))
    report["verdict"] = "critical" if failed else "none"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    summary_path = Path(os.environ["SUMMARY_PATH"])
    summary_path.write_text(append_commands(render_summary(report, failed), entries, approved))
    github.sync_label(number, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
