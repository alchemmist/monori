"""Provide shared pull-request report and command-reaction lifecycles."""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from monori.ci.lib.comments import CommandReactionLifecycle, Reaction, upsert_comment
from monori.ci.lib.github import GitHub, GitHubAPI

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping


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
class AdminControl:
    """One reversible administrator action rendered as a Markdown checkbox."""

    command: str
    reverse_command: str
    checked: bool = False

    @property
    def marker(self) -> str:
        """Encode both canonical commands in a stable hidden marker."""
        payload = f"{self.command}\n{self.reverse_command}".encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        return f"monori-qg-control:{encoded}"


@dataclass(frozen=True)
class AdminCommands:
    """Reversible administrator controls and explanatory notes."""

    controls: tuple[AdminControl, ...]
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
        definition = ALL_REPORTS.get(self.marker)
        if definition is None:
            message = f"Unknown Quality Graph report marker: {self.marker}"
            raise ValueError(message)
        return definition.title


@dataclass(frozen=True)
class ReportDefinition:
    """Stable marker and human-readable title for one Quality Graph report."""

    marker: str
    title: str


CHECK_REPORTS = {
    report.marker: report
    for report in (
        ReportDefinition("bundle-size", "Frontend bundle size"),
        ReportDefinition("frontend-performance", "Frontend performance"),
        ReportDefinition("mutation", "Mutation testing"),
        ReportDefinition("object-annotations", "Python object annotation gate"),
        ReportDefinition("suppression", "Lint suppression gate"),
    )
}
SURFACE_REPORTS = {
    "quality-graph": ReportDefinition("quality-graph", "Quality Graph"),
}
ALL_REPORTS = CHECK_REPORTS | SURFACE_REPORTS
TEMPLATE_DIRECTORY = Path(__file__).with_name("templates")
TEMPLATE_ENVIRONMENT = Environment(
    loader=FileSystemLoader(TEMPLATE_DIRECTORY),
    undefined=StrictUndefined,
    autoescape=select_autoescape(default=False),
    keep_trailing_newline=True,
    trim_blocks=False,
    lstrip_blocks=False,
)
REPORT_TEMPLATE = TEMPLATE_ENVIRONMENT.get_template("report.md.j2")


def finding_location(pr_url: str, path: str, line: int) -> ReportLocation:
    """Build a clickable pull-request diff location for a report finding."""
    diff_hash = hashlib.sha256(path.encode()).hexdigest()
    url = f"{pr_url.rstrip('/')}/files#diff-{diff_hash}R{line}"
    return ReportLocation(path, line, url)


def admin_commands(
    gate: str,
    active_ids: Collection[str],
    approved_ids: Collection[str],
    file_findings: Mapping[str, Collection[str]] | None = None,
    notes: Collection[str] = (),
) -> AdminCommands:
    """Build canonical administrator commands from one gate's current data."""
    active = sorted(set(active_ids))
    approved = sorted(set(approved_ids))
    controls: list[AdminControl] = []
    if active:
        remove_active = f"/qg remove-ignore {','.join(active)}"
        controls.extend(
            (
                AdminControl(f"/qg ignore {','.join(active)}", remove_active),
                AdminControl(f"/qg ignore {gate}", remove_active),
            )
        )
        for path, finding_ids in sorted((file_findings or {}).items()):
            selected = sorted(set(finding_ids))
            if selected:
                controls.append(
                    AdminControl(
                        f"/qg ignore-file {path}",
                        f"/qg remove-ignore {','.join(selected)}",
                    )
                )
    if approved:
        approved_command = f"/qg ignore {','.join(approved)}"
        controls.append(
            AdminControl(
                approved_command,
                f"/qg remove-ignore {','.join(approved)}",
                checked=True,
            )
        )
    return AdminCommands(tuple(controls), tuple(notes))


def render_report(model: ReportModel) -> str:
    """Render a complete report with the shared strict Jinja template."""
    rendered = re.sub(r"\n{3,}", "\n\n", REPORT_TEMPLATE.render(model=model).strip())
    return rendered + "\n"


@dataclass(frozen=True)
class PullRequestReport:
    """Own the complete lifecycle of one bot-managed pull-request report."""

    github: GitHubAPI
    number: int
    definition: ReportDefinition

    @classmethod
    def registered(cls, github: GitHubAPI, number: int, marker: str) -> PullRequestReport:
        """Create a report lifecycle from a registered marker."""
        definition = ALL_REPORTS.get(marker)
        if definition is None:
            message = f"Unknown Quality Graph report marker: {marker}"
            raise ValueError(message)
        return cls(github, number, definition)

    def publish(self, body: str) -> None:
        """Create or update this report's bot-owned comment."""
        upsert_comment(self.github, self.number, self.definition.marker, body)

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


def main() -> int:
    """Run report and reaction lifecycle operations from a composite action."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)

    progress = subparsers.add_parser("in-progress")
    progress.add_argument("--marker", choices=sorted(ALL_REPORTS), required=True)
    progress.add_argument("--pr-number", type=int, required=True)

    complete = subparsers.add_parser("complete")
    complete.add_argument("--marker", choices=sorted(ALL_REPORTS), required=True)
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
