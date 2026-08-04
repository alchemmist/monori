"""Provide shared pull-request report and command-reaction lifecycles."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from ci.lib.github import GITHUB_PAGE_SIZE, GitHub
from ci.lib.json import JsonValue, array_value, object_value

if TYPE_CHECKING:
    from collections.abc import Collection

DEFAULT_BOT_LOGIN = "github-actions[bot]"
LEGACY_BOT_LOGIN = "monori-bot"


class Reaction(StrEnum):
    """GitHub reaction values used by the command lifecycle."""

    ACKNOWLEDGED = "eyes"
    SUCCEEDED = "hooray"
    FAILED = "x"
    FORBIDDEN = "confused"


class ReportStatus(StrEnum):
    """Allowed visual states for every Quality Graph report."""

    PENDING = "pending"
    FAIL = "fail"
    DONE = "done"

    @property
    def emoji(self) -> str:
        """Return the only emoji allowed for this report state."""
        return {
            ReportStatus.PENDING: "⏳",
            ReportStatus.FAIL: "❌",
            ReportStatus.DONE: "✅",
        }[self]


@dataclass(frozen=True)
class ReportMetric:
    """One label-value row in the standard report metrics table."""

    label: str
    value: str


@dataclass(frozen=True)
class ReportLocation:
    """Clickable source location rendered consistently in report findings."""

    path: str
    line: int
    url: str

    @property
    def label(self) -> str:
        """Return the compact file-and-line label shown to the reader."""
        return f"{self.path}:{self.line}"


@dataclass(frozen=True)
class ReportFinding:
    """One rendered finding with its current approval state."""

    text: str
    approved: bool = False
    location: ReportLocation | None = None


@dataclass(frozen=True)
class AdminCommands:
    """Copy-paste administrator commands and explanatory notes."""

    commands: tuple[str, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportModel:
    """Typed data consumed by the shared Jinja report template."""

    marker: str
    status: ReportStatus
    message: str = ""
    metrics: tuple[ReportMetric, ...] = ()
    content: str = ""
    findings_title: str = "Findings"
    findings: tuple[ReportFinding, ...] = ()
    admin: AdminCommands | None = None

    @property
    def title(self) -> str:
        """Return the registered title for this report type."""
        definition = REPORTS.get(self.marker)
        if definition is None:
            message = f"Unknown Quality Graph report marker: {self.marker}"
            raise ValueError(message)
        return definition.title


@dataclass(frozen=True)
class ReportDefinition:
    """Stable marker and human-readable title for one Quality Graph report."""

    marker: str
    title: str


REPORTS = {
    report.marker: report
    for report in (
        ReportDefinition("bundle-size", "Frontend bundle size"),
        ReportDefinition("frontend-performance", "Frontend performance"),
        ReportDefinition("mutation", "Mutation testing"),
        ReportDefinition("object-annotations", "Python object annotation gate"),
        ReportDefinition("quality-graph", "Quality Graph"),
        ReportDefinition("suppression", "Lint suppression gate"),
    )
}
TEMPLATE_DIRECTORY = Path(__file__).with_name("templates")


def finding_location(pr_url: str, path: str, line: int) -> ReportLocation:
    """Build a clickable pull-request diff location for a report finding."""
    diff_hash = hashlib.sha256(path.encode()).hexdigest()
    url = f"{pr_url.rstrip('/')}/files#diff-{diff_hash}R{line}"
    return ReportLocation(path, line, url)


def admin_commands(
    gate: str,
    active_ids: Collection[str],
    approved_ids: Collection[str],
    file_paths: Collection[str] = (),
    notes: Collection[str] = (),
) -> AdminCommands:
    """Build canonical administrator commands from one gate's current data."""
    active = sorted(set(active_ids))
    approved = sorted(set(approved_ids))
    paths = sorted(set(file_paths))
    commands: list[str] = []
    if active:
        commands.extend((f"/qg ignore {','.join(active)}", f"/qg ignore {gate}"))
    if paths:
        commands.append(f"/qg ignore-file {','.join(paths)}")
    if approved:
        commands.append(f"/qg remove-ignore {','.join(approved)}")
    return AdminCommands(tuple(commands), tuple(notes))


def render_report(model: ReportModel) -> str:
    """Render a complete report with the shared strict Jinja template."""
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIRECTORY),
        undefined=StrictUndefined,
        autoescape=select_autoescape(default=False),
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    template = environment.get_template("report.md.j2")
    rendered = re.sub(r"\n{3,}", "\n\n", template.render(model=model).strip())
    return rendered + "\n"


class GitHubAPI(Protocol):
    """GitHub operations required by report and reaction lifecycles."""

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Execute one GitHub API request and return its decoded response."""
        ...


def workflow_bot_logins() -> set[str]:
    """Return logins allowed to own managed workflow comments and reactions."""
    configured = os.environ.get("GITHUB_ACTIONS_BOT_LOGIN", DEFAULT_BOT_LOGIN)
    return {configured, DEFAULT_BOT_LOGIN, LEGACY_BOT_LOGIN}


def issue_comments(github: GitHubAPI, number: int) -> list[dict[str, JsonValue]]:
    """Load every issue comment for a pull request."""
    result: list[dict[str, JsonValue]] = []
    for page in count(1):
        raw = github.request(
            "GET", f"/issues/{number}/comments?per_page={GITHUB_PAGE_SIZE}&page={page}"
        )
        items = array_value(raw, "pull request comments")
        result.extend(object_value(item, "pull request comment") for item in items)
        if len(items) < GITHUB_PAGE_SIZE:
            return result
    return result


def comment_body(marker: str, body: str) -> str:
    """Wrap report Markdown in its stable hidden marker."""
    return f"<!-- monori-report: {marker} -->\n\n{body.rstrip()}\n"


@dataclass(frozen=True)
class PullRequestReport:
    """Own the complete lifecycle of one bot-managed pull-request report."""

    github: GitHubAPI
    number: int
    definition: ReportDefinition

    @classmethod
    def registered(cls, github: GitHubAPI, number: int, marker: str) -> PullRequestReport:
        """Create a report lifecycle from a registered marker."""
        definition = REPORTS.get(marker)
        if definition is None:
            message = f"Unknown Quality Graph report marker: {marker}"
            raise ValueError(message)
        return cls(github, number, definition)

    def publish(self, body: str) -> None:
        """Create or update this report's bot-owned comment."""
        rendered = comment_body(self.definition.marker, body)
        marker = f"<!-- monori-report: {self.definition.marker} -->"
        bot_logins = workflow_bot_logins()
        for comment in issue_comments(self.github, self.number):
            comment_text = comment.get("body")
            author = object_value(comment.get("user", {}), "comment author").get("login")
            if not isinstance(comment_text, str) or marker not in comment_text:
                continue
            if author not in bot_logins:
                continue
            comment_id = comment.get("id")
            if not isinstance(comment_id, int):
                message = "Pull request report comment has no numeric id"
                raise TypeError(message)
            self.github.request("PATCH", f"/issues/comments/{comment_id}", {"body": rendered})
            return
        self.github.request("POST", f"/issues/{self.number}/comments", {"body": rendered})

    def mark_in_progress(self) -> None:
        """Replace stale report data with an explicit in-progress status."""
        self.publish(
            render_report(
                ReportModel(
                    self.definition.marker,
                    ReportStatus.PENDING,
                    "The check is running. This report will be updated when it finishes.",
                    (ReportMetric("Status", "⏳ In progress"),),
                )
            )
        )


@dataclass(frozen=True)
class CommandReactionLifecycle:
    """Manage acknowledgement and final reactions for one command comment."""

    github: GitHubAPI
    comment_id: int

    def set(self, reaction: Reaction) -> None:
        """Replace the workflow bot's previous reaction with the requested state."""
        reactions = array_value(
            self.github.request("GET", f"/issues/comments/{self.comment_id}/reactions"),
            "comment reactions",
        )
        bot_logins = workflow_bot_logins()
        for item in reactions:
            current = object_value(item, "reaction")
            user = object_value(current.get("user", {}), "reaction user")
            reaction_id = current.get("id")
            if user.get("login") in bot_logins and isinstance(reaction_id, int):
                self.github.request(
                    "DELETE", f"/issues/comments/{self.comment_id}/reactions/{reaction_id}"
                )
        self.github.request(
            "POST",
            f"/issues/comments/{self.comment_id}/reactions",
            {"content": reaction.value},
        )

    def acknowledge(self) -> None:
        """Mark the command as noticed and awaiting processing."""
        self.set(Reaction.ACKNOWLEDGED)

    def succeed(self) -> None:
        """Mark the command as successfully processed."""
        self.set(Reaction.SUCCEEDED)

    def fail(self) -> None:
        """Mark the command as invalid or unsuccessfully processed."""
        self.set(Reaction.FAILED)

    def forbid(self) -> None:
        """Mark the command as rejected because the author lacks permission."""
        self.set(Reaction.FORBIDDEN)


def main() -> int:
    """Run report and reaction lifecycle operations from a composite action."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)

    progress = subparsers.add_parser("in-progress")
    progress.add_argument("--marker", choices=sorted(REPORTS), required=True)
    progress.add_argument("--pr-number", type=int, required=True)

    complete = subparsers.add_parser("complete")
    complete.add_argument("--marker", choices=sorted(REPORTS), required=True)
    complete.add_argument("--pr-number", type=int, required=True)
    complete.add_argument(
        "--status",
        choices=[ReportStatus.DONE.value, ReportStatus.FAIL.value],
        required=True,
    )
    complete.add_argument("--body-file", type=Path)
    complete.add_argument("--message", default="")

    react = subparsers.add_parser("react")
    react.add_argument("--comment-id", type=int, required=True)
    react.add_argument(
        "--reaction",
        choices=[reaction.value for reaction in Reaction],
        required=True,
    )

    args = parser.parse_args()
    github = GitHub()
    if args.operation == "react":
        CommandReactionLifecycle(github, args.comment_id).set(Reaction(args.reaction))
        return 0
    report = PullRequestReport.registered(github, args.pr_number, args.marker)
    if args.operation == "in-progress":
        report.mark_in_progress()
    else:
        content = args.body_file.read_text() if args.body_file is not None else ""
        report.publish(
            render_report(
                ReportModel(
                    report.definition.marker,
                    ReportStatus(args.status),
                    args.message,
                    content=content,
                )
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
