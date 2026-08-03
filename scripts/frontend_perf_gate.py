"""Apply administrator approvals to a frontend performance report."""

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import cast

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

STATUS_LABEL = "monori-frontend-performance-failed"
FINDING_ID_PREFIX = "frontend-"
STATE_RE = re.compile(r"<!-- monori-frontend-performance-approvals: ([0-9a-f,]*) -->")
PENDING_RE = re.compile(r"<!-- monori-frontend-performance-pending: (\d+) -->")
COMMAND_RE = re.compile(r"^/(ignore|ignore-all|remove-ignore)(?:\s+(\S+))?$")
REQUEST_TIMEOUT = 30


def json_object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected an object for {context}")
    return value


def json_array(value: JsonValue, context: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise RuntimeError(f"Expected an array for {context}")
    return value


def optional_string(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def json_string(value: JsonValue, context: str) -> str:
    value = optional_string(value)
    if value is None:
        raise RuntimeError(f"Expected a string for {context}")
    return value


def json_integer(value: JsonValue, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"Expected an integer for {context}")
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


def finding_id(entry: dict[str, JsonValue]) -> str:
    route = json_string(entry.get("route_id"), "entry route id")
    metric = json_string(entry.get("metric_id"), "entry metric id")
    digest = hashlib.sha256(f"{route}:{metric}".encode()).hexdigest()[:12]
    return f"{FINDING_ID_PREFIX}{digest}"


class GitHub:
    def __init__(self) -> None:
        self.base_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repository = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        url = f"{self.base_url}/repos/{self.repository}{path}"
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return (
                    None
                    if response.status == 204
                    else cast(JsonValue, json.loads(response.read()))
                )
        except urllib.error.HTTPError as error:
            if error.code == 403 and method in {"POST", "PATCH", "DELETE"}:
                return None
            if error.code == 404 and method in {"GET", "DELETE"}:
                return None
            raise RuntimeError(f"GitHub API {method} {path} failed: HTTP {error.code}") from error

    def ensure_label(self, name: str) -> None:
        encoded = urllib.parse.quote(name, safe="")
        if self.request("GET", f"/labels/{encoded}") is None:
            self.request(
                "POST",
                "/labels",
                {"name": name, "color": "b60205", "description": "Frontend performance gate state"},
            )


def is_admin(github: GitHub, login: str) -> bool:
    encoded = urllib.parse.quote(login, safe="")
    permission = github.request("GET", f"/collaborators/{encoded}/permission")
    return (
        permission is not None
        and json_object(permission, "permission").get("permission") == "admin"
    )


def state_from_body(body: str) -> set[str]:
    match = STATE_RE.search(body)
    return set(match.group(1).split(",")) if match and match.group(1) else set()


def update_body_state(github: GitHub, number: int, body: str, approved: set[str]) -> str:
    marker = f"<!-- monori-frontend-performance-approvals: {','.join(sorted(approved))} -->"
    updated = STATE_RE.sub(marker, body)
    if updated == body:
        updated = f"{body.rstrip()}\n\n{marker}" if body.strip() else marker
    if updated != body:
        github.request("PATCH", f"/pulls/{number}", {"body": updated})
    return updated


def command_from_pending(github: GitHub, body: str) -> tuple[str, list[str] | None] | None:
    match = PENDING_RE.search(body)
    if not match:
        return None
    comment = json_object(github.request("GET", f"/issues/comments/{match.group(1)}"), "comment")
    command = parse_command((optional_string(comment.get("body")) or "").strip())
    author = json_object(comment.get("user", {}), "comment user")
    login = optional_string(author.get("login"))
    return command if command and login and is_admin(github, login) else None


def entry_ids(entries: list[dict[str, JsonValue]]) -> set[str]:
    return {finding_id(entry) for entry in entries if entry.get("tier") != "none"}


def apply_command(
    command: tuple[str, list[str] | None] | None,
    entries: list[dict[str, JsonValue]],
    approved: set[str],
) -> set[str]:
    if command is None:
        return approved
    name, arguments = command
    arguments = arguments or []
    ids = entry_ids(entries)
    if name == "ignore-all":
        return approved | ids
    selected = {
        argument
        for argument in arguments
        if argument.startswith(FINDING_ID_PREFIX)
    } & ids
    return approved - selected if name == "remove-ignore" else approved | selected


def append_commands(text: str, entries: list[dict[str, JsonValue]], approved: set[str]) -> str:
    lines = ["", "<details><summary>For repository administrators</summary>", ""]
    lines.append("Post exactly one command as a new pull-request comment:")
    lines.extend(
        [
            "",
            "- `/ignore frontend-<finding-id>[,frontend-<finding-id>...]`",
            "- `/ignore-all`",
            "- `/remove-ignore frontend-<finding-id>[,frontend-<finding-id>...]`",
            "",
        ]
    )
    lines.append("Performance findings:")
    for entry in entries:
        if entry.get("tier") == "none":
            continue
        marker = "✔" if finding_id(entry) in approved else "✗"
        route = json_string(entry.get("route_label"), "route label")
        metric = json_string(entry.get("metric_label"), "metric label")
        lines.append(f"- {marker} `{route} · {metric}` · `{finding_id(entry)}`")
    lines.extend(["", "</details>"])
    return text.rstrip() + "\n" + "\n".join(lines) + "\n"


def main() -> int:
    github = GitHub()
    report_path = Path(os.environ["REPORT_PATH"])
    report = json_object(cast(JsonValue, json.loads(report_path.read_text())), "report")
    entries = [
        json_object(item, "report entry")
        for item in json_array(report.get("entries"), "entries")
    ]
    number = json_integer(report.get("prNumber"), "pull request number")
    pull = json_object(github.request("GET", f"/pulls/{number}"), "pull request")
    body = optional_string(pull.get("body")) or ""
    approved = state_from_body(body) & entry_ids(entries)
    command = command_from_pending(github, body)
    approved = apply_command(command, entries, approved)
    if command is not None:
        body = PENDING_RE.sub("", body).rstrip()
    if command is not None or STATE_RE.search(body):
        body = update_body_state(github, number, body, approved)

    original_verdict = json_string(report.get("verdict"), "verdict")
    active = {
        finding_id(entry)
        for entry in entries
        if entry.get("tier") in {"critical", "error"} and finding_id(entry) not in approved
    }
    failed = bool(active) or original_verdict == "error"
    effective_verdict = original_verdict if failed else "none"
    report["verdict"] = effective_verdict
    report["commentRequired"] = failed
    report["approvedFindings"] = cast(JsonValue, sorted(approved))
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    summary_path = Path(os.environ["SUMMARY_PATH"])
    summary = summary_path.read_text()
    summary = re.sub(
        r"^## .*$",
        f"## {'❌' if failed else '✅'} Frontend performance",
        summary,
        count=1,
        flags=re.MULTILINE,
    )
    summary_path.write_text(append_commands(summary, entries, approved))
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
