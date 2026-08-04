"""Shared command API for the pull request Quality Graph."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from monori.ci.lib.comments import CommandReactionLifecycle, Reaction
from monori.ci.lib.github import GITHUB_PAGE_SIZE, GitHub, GitHubAPI
from monori.ci.quality_graph.reporting import (
    PullRequestReport,
    ReportModel,
    ReportStatus,
    render_report,
)
from monori.common import JsonValue, array_value, object_value, optional_string, string_value

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
    """Parsed `/qg` or `/quality-graph` command and its arguments."""

    name: CommandName
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandRequest:
    """Quality Graph command candidate extracted from an issue-comment event."""

    comment_id: int
    body: str
    login: str | None
    pull_request_number: int | None


@dataclass(frozen=True)
class CommandRejection:
    """Outcome to publish when a Quality Graph command cannot be processed."""

    detail: str
    reaction: Reaction
    command: QualityGraphCommand | None = None


def parse_command(body: str) -> QualityGraphCommand | None:
    """Parse a PR comment into a quality-graph command."""
    match = COMMAND_RE.fullmatch(body.strip())
    if not match:
        return None
    name = cast("CommandName", match.group(1) or "status")
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
    """Return True when `value` matches the typed finding id format."""
    return FINDING_ID_RE.fullmatch(value) is not None


def finding_gate(value: str) -> str | None:
    """Extract gate name from a finding id, if valid."""
    if not is_finding_id(value):
        return None
    return value.split("-", maxsplit=1)[0]


def is_gate_name(value: str) -> bool:
    """Check whether value is a valid gate name."""
    return GATE_NAME_RE.fullmatch(value) is not None


def command_targets_prefix(command: QualityGraphCommand, prefix: str) -> bool:
    """Check whether command arguments include an entry with given prefix."""
    return any(argument.startswith(prefix) for argument in command.arguments)


def command_targets_gate(command: QualityGraphCommand, gate: str) -> bool:
    """Check whether command targets the specified gate."""
    if command.name == "ignore-file":
        return gate in {"object", "suppression"}
    return gate in command.arguments or any(
        argument.startswith(f"{gate}-") for argument in command.arguments
    )


def validate_command(command: QualityGraphCommand) -> str | None:
    """Validate command arguments and return an error message or None."""
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
    """Render a normalized `/qg ...` command string."""
    suffix = f" {','.join(command.arguments)}" if command.arguments else ""
    return f"/qg {command.name}{suffix}"


def set_comment_reaction(github: GitHubAPI, comment_id: int, content: str) -> None:
    """Set a command reaction through the shared lifecycle."""
    CommandReactionLifecycle(github, comment_id).set(Reaction(content))


def upsert_status(github: GitHubAPI, number: int, body: str) -> None:
    """Update the Quality Graph status through the shared report lifecycle."""
    PullRequestReport.registered(github, number, "quality-graph").publish(body)


def is_admin(github: GitHubAPI, login: str) -> bool:
    """Return whether admin."""
    encoded = urllib.parse.quote(login, safe="")
    permission = github.request("GET", f"/collaborators/{encoded}/permission")
    return (
        permission is not None
        and object_value(permission, "collaborator permission").get("permission") == "admin"
    )


def pull_request_number(event: dict[str, JsonValue]) -> int | None:
    """Pull request number for this module."""
    issue = object_value(event.get("issue", {}), "event issue")
    if not issue.get("pull_request"):
        return None
    number = issue.get("number")
    return number if isinstance(number, int) else None


def command_result(command: QualityGraphCommand, status: ReportStatus, detail: str) -> str:
    """Render a command result with the shared Quality Graph template."""
    return render_report(
        ReportModel(
            "quality-graph",
            status,
            detail,
            content=f"Command: `{command_text(command)}`",
        )
    )


def help_body() -> str:
    """Render command help with the shared Quality Graph template."""
    return render_report(
        ReportModel(
            "quality-graph",
            ReportStatus.DONE,
            "Only repository administrators may execute state-changing commands.",
            content="""- `/qg ignore object-<id>,suppression-<id>` — ignore selected findings
- `/qg ignore object,suppression` — ignore all current findings of selected types
- `/qg ignore-file path/to/file` — ignore findings in selected files
- `/qg remove-ignore object-<id>,suppression-<id>` — remove selected ignores
- `/qg status` — show the current command status
- `/qg help` — show this help""",
        )
    )


def read_event() -> dict[str, JsonValue]:
    """Read the GitHub event payload from the path supplied by Actions."""
    return cast(
        "dict[str, JsonValue]",
        json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()),
    )


def is_quality_graph_command(body: str) -> bool:
    """Return whether a comment body addresses the Quality Graph command API."""
    return body in {"/qg", "/quality-graph"} or body.startswith(("/qg ", "/quality-graph "))


def command_request(event: dict[str, JsonValue]) -> CommandRequest | None:
    """Extract a Quality Graph command request from an issue-comment event."""
    comment = object_value(event.get("comment", {}), "event comment")
    comment_id = comment.get("id")
    if not isinstance(comment_id, int):
        return None
    comment_body = string_value(comment.get("body"), "comment body").strip()
    if not is_quality_graph_command(comment_body):
        return None
    author = object_value(comment.get("user", {}), "comment user")
    return CommandRequest(
        comment_id,
        comment_body,
        optional_string(author.get("login")),
        pull_request_number(event),
    )


def publish_rejection(
    github: GitHubAPI,
    request: CommandRequest,
    rejection: CommandRejection,
) -> None:
    """Publish a rejected command result and apply its final reaction."""
    if request.pull_request_number is not None:
        body = (
            command_result(rejection.command, ReportStatus.FAIL, rejection.detail)
            if rejection.command is not None
            else render_report(ReportModel("quality-graph", ReportStatus.FAIL, rejection.detail))
        )
        upsert_status(github, request.pull_request_number, body)
    CommandReactionLifecycle(github, request.comment_id).set(rejection.reaction)


def process_command(github: GitHubAPI, request: CommandRequest) -> None:
    """Validate, authorize, and dispatch one Quality Graph command request."""
    command = parse_command(request.body)
    reactions = CommandReactionLifecycle(github, request.comment_id)
    reactions.acknowledge()
    if command is None:
        publish_rejection(
            github,
            request,
            CommandRejection("Unknown command. Use `/qg help`.", Reaction.FAILED),
        )
        return
    validation_error = validate_command(command)
    if validation_error is not None:
        publish_rejection(
            github,
            request,
            CommandRejection(validation_error, Reaction.FAILED, command),
        )
        return
    number = request.pull_request_number
    if number is None or request.login is None or not is_admin(github, request.login):
        publish_rejection(
            github,
            request,
            CommandRejection(
                "Only repository administrators may execute Quality Graph commands.",
                Reaction.FORBIDDEN,
                command,
            ),
        )
        return
    try:
        if command.name == "help":
            upsert_status(github, number, help_body())
        elif command.name == "status":
            upsert_status(
                github,
                number,
                render_report(
                    ReportModel(
                        "quality-graph",
                        ReportStatus.DONE,
                        "Command API is available and ready to process administrator commands.",
                    )
                ),
            )
        else:
            apply_gate_command(github, number, request.comment_id, command)
    except (RuntimeError, TypeError, ValueError):
        reactions.fail()
        raise
    reactions.succeed()


def apply_gate_command(
    github: GitHubAPI,
    number: int,
    comment_id: int,
    command: QualityGraphCommand,
) -> None:
    """Store a gate command marker on the pull request and rerun the graph."""
    upsert_status(
        github,
        number,
        command_result(
            command,
            ReportStatus.PENDING,
            "Command accepted. Applying it and refreshing the Quality Graph.",
        ),
    )
    pull = object_value(github.request("GET", f"/pulls/{number}"), "pull request")
    original_body = pull.get("body")
    body = string_value(original_body, "pull request body") if original_body is not None else ""
    for gate, marker_name in {
        "bundle": "monori-bundle-size-pending",
        "frontend": "monori-frontend-performance-pending",
    }.items():
        if command_targets_gate(command, gate):
            marker = f"<!-- {marker_name}: {comment_id} -->"
            body = re.sub(rf"<!-- {marker_name}: \d+ -->", marker, body)
            if marker not in body:
                body = f"{body.rstrip()}\n\n{marker}".strip()
    if body != (original_body or ""):
        github.request("PATCH", f"/pulls/{number}", {"body": body})
    rerun_workflow(github, number)


def main() -> int:
    """Run the Quality Graph command handler for the current GitHub event."""
    request = command_request(read_event())
    if request is not None:
        process_command(GitHub(), request)
    return 0


def rerun_workflow(github: GitHubAPI, number: int) -> None:
    """Rerun workflow for this module."""
    pull = object_value(github.request("GET", f"/pulls/{number}"), "pull request")
    head = object_value(pull.get("head", {}), "pull request head")
    sha = string_value(head.get("sha"), "pull request head sha")
    branch = string_value(head.get("ref"), "pull request head branch")
    for page in range(1, GITHUB_PAGE_SIZE + 1):
        response = object_value(
            github.request(
                "GET",
                f"/actions/workflows/pr-checks.yaml/runs?event=pull_request&branch={urllib.parse.quote(branch)}&per_page={GITHUB_PAGE_SIZE}&page={page}",
            ),
            "workflow runs response",
        )
        runs = array_value(response.get("workflow_runs"), "workflow runs")
        for item in runs:
            run = object_value(item, "workflow run")
            if run.get("head_sha") == sha and isinstance(run.get("id"), int):
                github.request("POST", f"/actions/runs/{run['id']}/rerun-failed-jobs")
                return
        if len(runs) < GITHUB_PAGE_SIZE:
            break
    message = f"No completed pr-checks.yaml run found for PR #{number}"
    raise RuntimeError(message)


if __name__ == "__main__":
    raise SystemExit(main())
