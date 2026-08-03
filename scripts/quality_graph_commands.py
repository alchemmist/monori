"""Shared command API for the pull request Quality Graph."""

from __future__ import annotations

import re
from dataclasses import dataclass
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Collection, Literal, Protocol, cast

CommandName = Literal["help", "status", "ignore", "ignore-file", "remove-ignore"]
COMMAND_RE = re.compile(
    r"^/(?:quality-graph|qg)(?:\s+(help|status|ignore|ignore-file|remove-ignore)"
    r"(?:\s+(\S+))?)?$"
)
GATE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
FINDING_ID_RE = re.compile(r"^[a-z][a-z0-9-]*-[a-z0-9-]+$")
KNOWN_GATES = {"object", "suppression", "bundle", "frontend"}


@dataclass(frozen=True)
class QualityGraphCommand:
    name: CommandName
    arguments: tuple[str, ...] = ()


def parse_command(body: str) -> QualityGraphCommand | None:
    match = COMMAND_RE.fullmatch(body.strip())
    if not match:
        return None
    name = cast(CommandName, match.group(1) or "status")
    argument = match.group(2)
    if name in {"help", "status"}:
        return QualityGraphCommand(name) if argument is None else None
    if argument is None:
        return None
    arguments = tuple(item.strip() for item in argument.split(","))
    if not all(arguments) or "all" in arguments:
        return None
    return QualityGraphCommand(name, arguments)


def is_finding_id(value: str) -> bool:
    return FINDING_ID_RE.fullmatch(value) is not None


def finding_gate(value: str) -> str | None:
    if not is_finding_id(value):
        return None
    return value.split("-", maxsplit=1)[0]


def is_gate_name(value: str) -> bool:
    return GATE_NAME_RE.fullmatch(value) is not None


def command_targets_prefix(command: QualityGraphCommand, prefix: str) -> bool:
    return any(argument.startswith(prefix) for argument in command.arguments)


def command_targets_gate(command: QualityGraphCommand, gate: str) -> bool:
    if command.name == "ignore-file":
        return gate in {"object", "suppression"}
    return gate in command.arguments or any(
        argument.startswith(f"{gate}-") for argument in command.arguments
    )


def validate_command(command: QualityGraphCommand) -> str | None:
    if command.name in {"help", "status"}:
        return None
    if command.name == "ignore-file":
        return None if all(command.arguments) else "At least one file path is required"
    for argument in command.arguments:
        if argument in KNOWN_GATES or finding_gate(argument) in KNOWN_GATES:
            continue
        return f"Unknown Quality Graph target: `{argument}`"
    return None if command.arguments else "At least one target is required"


def command_text(command: QualityGraphCommand) -> str:
    suffix = f" {','.join(command.arguments)}" if command.arguments else ""
    return f"/qg {command.name}{suffix}"


def admin_command_lines(
    gate: str,
    active_ids: Collection[str],
    approved_ids: Collection[str],
    file_paths: Collection[str] = (),
) -> list[str]:
    """Render copy-paste commands for the findings in one gate report."""
    active = sorted(set(active_ids))
    approved = sorted(set(approved_ids))
    paths = sorted(set(file_paths))
    lines = ["Post exactly one command as a new pull-request comment:", ""]
    if active:
        lines.append(f"- `/qg ignore {','.join(active)}`")
        lines.append(f"- `/qg ignore {gate}`")
    if paths:
        lines.append(f"- `/qg ignore-file {','.join(paths)}`")
    if approved:
        lines.append(f"- `/qg remove-ignore {','.join(approved)}`")
    if not active and not paths and not approved:
        lines.append("No actionable findings in this run.")
    return lines


type JsonValue = (
    bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
)


def json_object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected object for {context}")
    return value


def json_array(value: JsonValue, context: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise RuntimeError(f"Expected array for {context}")
    return value


def json_string(value: JsonValue, context: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"Expected string for {context}")
    return value


class GitHubAPI(Protocol):
    def request(
        self, method: str, path: str, payload: JsonValue = None
    ) -> JsonValue: ...


class GitHub:
    def __init__(self) -> None:
        self.base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repository = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        data = None if payload is None else json.dumps(payload).encode()
        api_path = path if path == "/user" else f"/repos/{self.repository}{path}"
        request = urllib.request.Request(
            f"{self.base}{api_path}",
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
            with urllib.request.urlopen(request, timeout=30) as response:
                return (
                    None
                    if response.status == 204
                    else cast(JsonValue, json.loads(response.read()))
                )
        except urllib.error.HTTPError as error:
            if error.code == 403 and method in {"POST", "PATCH", "DELETE"}:
                return None
            raise RuntimeError(
                f"GitHub API {method} {path} failed: HTTP {error.code}"
            ) from error


def bot_login(github: GitHubAPI) -> str:
    return json_string(
        json_object(github.request("GET", "/user"), "authenticated user").get("login"),
        "bot login",
    )


def set_comment_reaction(github: GitHubAPI, comment_id: int, content: str) -> None:
    reactions = json_array(
        github.request("GET", f"/issues/comments/{comment_id}/reactions"),
        "comment reactions",
    )
    login = bot_login(github)
    for item in reactions:
        reaction = json_object(item, "reaction")
        user = json_object(reaction.get("user", {}), "reaction user")
        reaction_id = reaction.get("id")
        if user.get("login") == login and isinstance(reaction_id, int):
            github.request(
                "DELETE", f"/issues/comments/{comment_id}/reactions/{reaction_id}"
            )
    github.request(
        "POST", f"/issues/comments/{comment_id}/reactions", {"content": content}
    )


def upsert_status(github: GitHubAPI, number: int, body: str) -> None:
    marker = "<!-- monori-report: quality-graph -->"
    rendered = f"{marker}\n\n{body.rstrip()}\n"
    login = bot_login(github)
    for page in range(1, 101):
        comments = json_array(
            github.request(
                "GET", f"/issues/{number}/comments?per_page=100&page={page}"
            ),
            "pull request comments",
        )
        for item in comments:
            comment = json_object(item, "pull request comment")
            author = json_object(comment.get("user", {}), "comment author")
            if (
                marker not in str(comment.get("body", ""))
                or author.get("login") != login
            ):
                continue
            comment_id = comment.get("id")
            if not isinstance(comment_id, int):
                raise RuntimeError("Quality Graph comment has no numeric id")
            github.request(
                "PATCH", f"/issues/comments/{comment_id}", {"body": rendered}
            )
            return
        if len(comments) < 100:
            break
    github.request("POST", f"/issues/{number}/comments", {"body": rendered})


def is_admin(github: GitHubAPI, login: str) -> bool:
    encoded = urllib.parse.quote(login, safe="")
    permission = github.request("GET", f"/collaborators/{encoded}/permission")
    return (
        permission is not None
        and json_object(permission, "collaborator permission").get("permission")
        == "admin"
    )


def pull_request_number(event: dict[str, JsonValue]) -> int | None:
    issue = json_object(event.get("issue", {}), "event issue")
    if not issue.get("pull_request"):
        return None
    number = issue.get("number")
    return number if isinstance(number, int) else None


def command_result(command: QualityGraphCommand, status: str, detail: str) -> str:
    return "\n".join(
        [
            f"## Quality Graph command {status}",
            "",
            f"`{command_text(command)}`",
            "",
            detail,
        ]
    )


def help_body() -> str:
    return "\n".join(
        [
            "## Quality Graph commands",
            "",
            "Only repository administrators may execute state-changing commands.",
            "",
            "- `/qg ignore object-<id>,suppression-<id>` — ignore selected findings",
            "- `/qg ignore object,suppression` — ignore all current findings of selected types",
            "- `/qg ignore-file path/to/file` — ignore findings in selected files",
            "- `/qg remove-ignore object-<id>,suppression-<id>` — remove selected ignores",
            "- `/qg status` — show the current command status",
            "- `/qg help` — show this help",
        ]
    )


def main() -> int:
    event = cast(
        dict[str, JsonValue],
        json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()),
    )
    comment = json_object(event.get("comment", {}), "event comment")
    comment_id = comment.get("id")
    if not isinstance(comment_id, int):
        return 0
    comment_body = json_string(comment.get("body"), "comment body").strip()
    if not (
        comment_body == "/qg"
        or comment_body.startswith("/qg ")
        or comment_body == "/quality-graph"
        or comment_body.startswith("/quality-graph ")
    ):
        return 0
    command = parse_command(comment_body)
    github = GitHub()
    number = pull_request_number(event)
    if command is None:
        set_comment_reaction(github, comment_id, "eyes")
        if number is not None:
            upsert_status(
                github,
                number,
                "## Quality Graph command ❌\n\nUnknown command. Use `/qg help`.",
            )
        set_comment_reaction(github, comment_id, "-1")
        return 0
    validation_error = validate_command(command)
    author = json_object(comment.get("user", {}), "comment user")
    login = json_string(author.get("login"), "comment author")
    if validation_error is not None:
        set_comment_reaction(github, comment_id, "eyes")
        if number is not None:
            upsert_status(
                github, number, command_result(command, "❌", validation_error)
            )
        set_comment_reaction(github, comment_id, "-1")
        return 0
    set_comment_reaction(github, comment_id, "eyes")
    if number is None or not is_admin(github, login):
        set_comment_reaction(github, comment_id, "confused")
        if number is not None:
            upsert_status(
                github,
                number,
                command_result(
                    command,
                    "😕",
                    "Only repository administrators may execute Quality Graph commands.",
                ),
            )
        return 0
    if command.name == "help":
        upsert_status(github, number, help_body())
        set_comment_reaction(github, comment_id, "hooray")
        return 0
    if command.name == "status":
        upsert_status(
            github,
            number,
            "## Quality Graph status\n\nCommand API is available and ready to process administrator commands.",
        )
        set_comment_reaction(github, comment_id, "hooray")
        return 0
    upsert_status(
        github,
        number,
        command_result(
            command,
            "👀",
            "Command accepted. Applying it and refreshing the Quality Graph.",
        ),
    )
    set_comment_reaction(github, comment_id, "hooray")
    pull = json_object(github.request("GET", f"/pulls/{number}"), "pull request")
    body = (
        json_string(pull.get("body"), "pull request body")
        if pull.get("body") is not None
        else ""
    )
    markers = {
        "bundle": "monori-bundle-size-pending",
        "frontend": "monori-frontend-performance-pending",
    }
    for gate, marker_name in markers.items():
        if command_targets_gate(command, gate):
            marker = f"<!-- {marker_name}: {comment_id} -->"
            pattern = re.compile(rf"<!-- {marker_name}: \d+ -->")
            body = pattern.sub(marker, body)
            if marker not in body:
                body = f"{body.rstrip()}\n\n{marker}".strip()
    if body != (pull.get("body") or ""):
        github.request("PATCH", f"/pulls/{number}", {"body": body})
    if command.name not in {"help", "status"}:
        rerun_workflow(github, number)
    return 0


def rerun_workflow(github: GitHubAPI, number: int) -> None:
    pull = json_object(github.request("GET", f"/pulls/{number}"), "pull request")
    head = json_object(pull.get("head", {}), "pull request head")
    sha = json_string(head.get("sha"), "pull request head sha")
    branch = json_string(head.get("ref"), "pull request head branch")
    for page in range(1, 101):
        response = json_object(
            github.request(
                "GET",
                f"/actions/workflows/pr-checks.yaml/runs?event=pull_request&branch={urllib.parse.quote(branch)}&per_page=100&page={page}",
            ),
            "workflow runs response",
        )
        runs = json_array(response.get("workflow_runs"), "workflow runs")
        for item in runs:
            run = json_object(item, "workflow run")
            if run.get("head_sha") == sha and isinstance(run.get("id"), int):
                github.request("POST", f"/actions/runs/{run['id']}/rerun-failed-jobs")
                return
        if len(runs) < 100:
            break
    raise RuntimeError(f"No completed pr-checks.yaml run found for PR #{number}")


if __name__ == "__main__":
    raise SystemExit(main())
