"""Shared command API for the pull request Quality Graph."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from monori.ci.lib.comments import (
    CommandReactionLifecycle,
    Reaction,
    managed_comment,
    workflow_bot_logins,
)
from monori.ci.lib.github import GitHub, GitHubAPI, rerun_latest_pull_request_workflow
from monori.ci.lib.github import is_admin as github_is_admin
from monori.ci.quality_graph.registry import registered_checks
from monori.ci.quality_graph.reporting import (
    PullRequestReport,
    ReportModel,
    ReportStatus,
    render_report,
)
from monori.common import JsonValue, object_value, optional_string, string_value

CommandName = Literal["help", "status", "ignore", "ignore-file", "remove-ignore"]
COMMAND_RE = re.compile(
    r"^/(?:quality-graph|qg)(?:\s+(help|status|ignore|ignore-file|remove-ignore)"
    r"(?:\s+(\S+))?)?$"
)
GATE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
FINDING_ID_RE = re.compile(r"^[a-z][a-z0-9-]*-[a-z0-9-]+$")
CONTROL_COMMAND_COUNT = 2
CONTROL_RE = re.compile(
    r"^- \[(?P<state>[ xX])] .*?<!-- (?P<marker>monori-qg-control:[A-Za-z0-9_-]+) -->$",
    re.MULTILINE,
)


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
    react: bool = True


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
    check = registered_checks().get(gate)
    if check is None:
        return False
    if command.name == "ignore-file":
        return check.supports_ignore_file
    return gate in command.arguments or any(
        argument.startswith(f"{gate}-") for argument in command.arguments
    )


def validate_command(command: QualityGraphCommand) -> str | None:
    """Validate command arguments and return an error message or None."""
    checks = registered_checks()
    if command.name in {"help", "status"}:
        return None
    if command.name == "ignore-file":
        return None if all(command.arguments) else "At least one file path is required"
    for argument in command.arguments:
        if argument in checks or finding_gate(argument) in checks:
            continue
        return f"Unknown Quality Graph target: `{argument}`"
    return None if command.arguments else "At least one target is required"


def command_text(command: QualityGraphCommand) -> str:
    """Render a normalized `/qg ...` command string."""
    suffix = f" {','.join(command.arguments)}" if command.arguments else ""
    return f"/qg {command.name}{suffix}"


def encode_command(command: QualityGraphCommand) -> str:
    """Encode a canonical command for storage in a pull-request marker."""
    return base64.urlsafe_b64encode(command_text(command).encode()).decode().rstrip("=")


def decode_command(encoded: str) -> QualityGraphCommand | None:
    """Decode and parse a canonical command stored in a pull-request marker."""
    try:
        body = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    return parse_command(body)


def set_comment_reaction(github: GitHubAPI, comment_id: int, content: str) -> None:
    """Set a command reaction through the shared lifecycle."""
    CommandReactionLifecycle(github, comment_id).set(Reaction(content))


def upsert_status(github: GitHubAPI, number: int, body: str) -> None:
    """Update the Quality Graph status through the shared report lifecycle."""
    PullRequestReport.registered(github, number, "quality-graph").publish(body)


def is_admin(github: GitHubAPI, login: str) -> bool:
    """Delegate repository permission checks to the shared GitHub layer."""
    return github_is_admin(github, login)


def pull_request_number(event: dict[str, JsonValue]) -> int | None:
    """Return the pull-request number from an issue event, or `None` for regular issues."""
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
    raw_comment = event.get("comment")
    if not isinstance(raw_comment, dict):
        return None
    comment = object_value(raw_comment, "event comment")
    comment_id = comment.get("id")
    if not isinstance(comment_id, int):
        return None
    comment_body = string_value(comment.get("body"), "comment body").strip()
    if not is_quality_graph_command(comment_body):
        return checkbox_command_request(event, comment_id, comment_body)
    author = object_value(comment.get("user", {}), "comment user")
    return CommandRequest(
        comment_id,
        comment_body,
        optional_string(author.get("login")),
        pull_request_number(event),
    )


def control_states(body: str) -> dict[str, bool]:
    """Extract checkbox states keyed by their hidden control marker."""
    return {
        match.group("marker"): match.group("state").lower() == "x"
        for match in CONTROL_RE.finditer(body)
    }


def control_commands(marker: str) -> tuple[str, str] | None:
    """Decode the apply and reverse commands stored in a control marker."""
    encoded = marker.removeprefix("monori-qg-control:")
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    commands = payload.splitlines()
    if len(commands) != CONTROL_COMMAND_COUNT or any(
        parse_command(command) is None for command in commands
    ):
        return None
    return commands[0], commands[1]


def checkbox_command_request(
    event: dict[str, JsonValue], comment_id: int, body: str
) -> CommandRequest | None:
    """Convert one administrator checkbox edit into a canonical command request."""
    if event.get("action") != "edited":
        return None
    comment = object_value(event.get("comment", {}), "event comment")
    author = object_value(comment.get("user", {}), "comment user")
    if author.get("login") not in workflow_bot_logins():
        return None
    changes = object_value(event.get("changes", {}), "event changes")
    body_change = object_value(changes.get("body", {}), "comment body change")
    previous_body = string_value(body_change.get("from"), "previous comment body")
    before = control_states(previous_body)
    after = control_states(body)
    changed = [marker for marker in before.keys() & after.keys() if before[marker] != after[marker]]
    if len(changed) != 1:
        return None
    commands = control_commands(changed[0])
    if commands is None:
        return None
    apply_command, reverse_command = commands
    sender = object_value(event.get("sender", {}), "event sender")
    selected_command = apply_command if after[changed[0]] else reverse_command
    return CommandRequest(
        comment_id,
        selected_command,
        optional_string(sender.get("login")),
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
    if request.react:
        reactions.acknowledge()
    if command is None:
        reject_request(
            github,
            request,
            CommandRejection("Unknown command. Use `/qg help`.", Reaction.FAILED),
        )
        return
    validation_error = validate_command(command)
    if validation_error is not None:
        reject_request(
            github,
            request,
            CommandRejection(validation_error, Reaction.FAILED, command),
        )
        return
    number = request.pull_request_number
    if number is None or request.login is None or not is_admin(github, request.login):
        reject_request(
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
        dispatch_command(github, number, command)
    except (RuntimeError, TypeError, ValueError):
        if request.react:
            reactions.fail()
        raise
    if request.react:
        reactions.succeed()


def reject_request(github: GitHubAPI, request: CommandRequest, rejection: CommandRejection) -> None:
    """Reject a request visibly only when it originated as a command comment."""
    if request.react:
        publish_rejection(github, request, rejection)


def dispatch_command(
    github: GitHubAPI,
    number: int,
    command: QualityGraphCommand,
) -> None:
    """Dispatch one validated and authorized command."""
    if command.name == "help":
        upsert_status(github, number, help_body())
        return
    if command.name == "status":
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
        return
    apply_gate_command(github, number, command)


def apply_gate_command(
    github: GitHubAPI,
    number: int,
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
    for gate, check in registered_checks().items():
        marker_name = check.pending_marker
        if marker_name is None:
            continue
        if command_targets_gate(command, gate):
            encoded = encode_command(command)
            report = managed_comment(github, number, check.report_marker)
            if report is None:
                message = f"Cannot authorize {gate} command without its managed report"
                raise RuntimeError(message)
            report_id = report.get("id")
            if not isinstance(report_id, int):
                message = f"Managed {gate} report has no numeric comment id"
                raise TypeError(message)
            report_body = string_value(report.get("body"), "report comment body")
            authorization = f"<!-- monori-qg-authorized: {gate} {encoded} -->"
            cleaned = re.sub(
                rf"\n?<!-- monori-qg-authorized: {gate} [A-Za-z0-9_-]+ -->",
                "",
                report_body,
            )
            github.request(
                "PATCH",
                f"/issues/comments/{report_id}",
                {"body": f"{cleaned.rstrip()}\n{authorization}\n"},
            )
            marker = f"<!-- {marker_name}: {report_id} {encoded} -->"
            body = re.sub(rf"<!-- {marker_name}: \d+(?: [A-Za-z0-9_-]+)? -->", marker, body)
            if marker not in body:
                body = f"{body.rstrip()}\n\n{marker}".strip()
    if body != (original_body or ""):
        github.request("PATCH", f"/pulls/{number}", {"body": body})
    rerun_latest_pull_request_workflow(github, number)


def main() -> int:
    """Run the Quality Graph command handler for the current GitHub event."""
    request = command_request(read_event())
    if request is not None:
        process_command(GitHub(), request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
