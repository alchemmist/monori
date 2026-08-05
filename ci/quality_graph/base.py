"""Base contract for declarative Quality Graph checks."""

from __future__ import annotations

import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Protocol

from monori.ci.lib.comments import workflow_bot_logins
from monori.ci.lib.github import is_admin
from monori.ci.quality_graph.commands import (
    QualityGraphCommand,
    decode_command,
    parse_command,
    validate_command,
)
from monori.ci.quality_graph.models import CheckContext, CheckResult, FindingProtocol
from monori.ci.quality_graph.reporting import REPORTS, PullRequestReport
from monori.common import JsonValue, object_value, optional_string

if TYPE_CHECKING:
    from collections.abc import Sequence
    from re import Pattern

    from monori.ci.lib.github import GitHubAPI


class ApprovableFinding(FindingProtocol, Protocol):
    """Describe fields required by the shared approval lifecycle."""

    @property
    def path(self) -> str:
        """Return the repository-relative source path."""
        ...


@dataclass(frozen=True)
class ApprovalSyncResult:
    """Return the effective approvals and command execution outcome."""

    approved: set[str]
    authorized: bool
    changed: bool


@dataclass(frozen=True)
class ApprovalRequest:
    """Bundle GitHub and command state needed to synchronize approvals."""

    github: GitHubAPI
    number: int
    body: str
    command: QualityGraphCommand | None
    author: str | None
    labels: list[dict[str, JsonValue]]


@dataclass(frozen=True)
class ApprovalLifecycle:
    """Manage persistent approvals and pending commands for one gate."""

    gate: str
    finding_prefix: str
    state_pattern: Pattern[str]
    state_marker: str
    pending_pattern: Pattern[str] | None = None
    legacy_label_prefix: str | None = None

    def read(self, body: str) -> set[str]:
        """Read finding IDs from the pull-request state marker."""
        match = self.state_pattern.search(body)
        return set(match.group(1).split(",")) if match and match.group(1) else set()

    def persist_approvals(
        self, github: GitHubAPI, number: int, body: str, approved: set[str]
    ) -> str:
        """Persist finding IDs in the pull-request state marker."""
        marker = self.state_marker.format(ids=",".join(sorted(approved)))
        updated = self.state_pattern.sub(marker, body)
        if updated == body:
            updated = f"{body.rstrip()}\n\n{marker}" if body.strip() else marker
        if updated != body:
            github.request("PATCH", f"/pulls/{number}", {"body": updated})
        return updated

    def pending_command(self, github: GitHubAPI, body: str) -> QualityGraphCommand | None:
        """Resolve and authorize a command referenced by a pending marker."""
        if self.pending_pattern is None or (match := self.pending_pattern.search(body)) is None:
            return None
        raw_comment = github.request("GET", f"/issues/comments/{match.group(1)}")
        if not isinstance(raw_comment, dict):
            return None
        comment = object_value(raw_comment, "command comment")
        user = object_value(comment.get("user", {}), "command author")
        login = optional_string(user.get("login"))
        if match.group(2):
            encoded = match.group(2)
            command = decode_command(encoded)
            comment_body = optional_string(comment.get("body")) or ""
            authorization = self.authorization_marker(encoded)
            if login not in workflow_bot_logins() or authorization not in comment_body:
                return None
            return command if command is not None and validate_command(command) is None else None
        command = parse_command((optional_string(comment.get("body")) or "").strip())
        if command is None or validate_command(command) is not None or login is None:
            return None
        return command if is_admin(github, login) else None

    def authorization_marker(self, encoded_command: str) -> str:
        """Render the bot-owned one-time authorization marker for a command."""
        return f"<!-- monori-qg-authorized: {self.gate} {encoded_command} -->"

    def consume_pending(self, github: GitHubAPI, body: str) -> None:
        """Remove a consumed command authorization from its bot-owned comment."""
        if self.pending_pattern is None or (match := self.pending_pattern.search(body)) is None:
            return
        encoded = match.group(2)
        if encoded is None:
            return
        comment_id = int(match.group(1))
        comment = object_value(
            github.request("GET", f"/issues/comments/{comment_id}"), "command comment"
        )
        comment_body = optional_string(comment.get("body")) or ""
        marker = self.authorization_marker(encoded)
        updated = comment_body.replace(f"\n{marker}", "").replace(marker, "")
        if updated != comment_body:
            github.request("PATCH", f"/issues/comments/{comment_id}", {"body": updated})

    def without_pending(self, body: str) -> str:
        """Remove this gate's pending command marker from a PR body."""
        return (
            self.pending_pattern.sub("", body).rstrip()
            if self.pending_pattern is not None
            else body
        )

    def sync(
        self,
        request: ApprovalRequest,
        findings: Sequence[ApprovableFinding],
    ) -> ApprovalSyncResult:
        """Apply an authorized command and persist effective approvals."""
        finding_ids = {finding.finding_id for finding in findings}
        state_exists = self.state_pattern.search(request.body) is not None
        approved = (
            self.read(request.body)
            if state_exists
            else self._legacy_approvals(request.labels, finding_ids)
        )
        self._remove_legacy_labels(request.github, request.number, request.labels)
        approved &= finding_ids
        authorized = (
            request.command is not None
            and request.author is not None
            and is_admin(request.github, request.author)
        )
        changed = False
        if (
            request.command is not None
            and authorized
            and request.command.name not in {"help", "status"}
        ):
            selected = self._selected(request.command, findings)
            approved = (
                approved - selected
                if request.command.name == "remove-ignore"
                else approved | selected
            )
            changed = bool(selected)
        if not state_exists or (request.command is not None and authorized):
            self.persist_approvals(request.github, request.number, request.body, approved)
        return ApprovalSyncResult(approved, authorized, changed)

    def _selected(
        self, command: QualityGraphCommand, findings: Sequence[ApprovableFinding]
    ) -> set[str]:
        """Select findings addressed by a canonical Quality Graph command."""
        all_ids = {finding.finding_id for finding in findings}
        if command.name == "ignore-file":
            return {finding.finding_id for finding in findings if finding.path in command.arguments}
        if command.name not in {"ignore", "remove-ignore"}:
            return set()
        if self.gate in command.arguments:
            return all_ids
        return {
            argument.removeprefix(self.finding_prefix)
            for argument in command.arguments
            if argument.startswith(self.finding_prefix)
        } & all_ids

    def _legacy_approvals(
        self, labels: list[dict[str, JsonValue]], finding_ids: set[str]
    ) -> set[str]:
        """Read and remove labels used by the legacy approval implementation."""
        if self.legacy_label_prefix is None:
            return set()
        return {
            name.removeprefix(self.legacy_label_prefix)
            for label in labels
            if isinstance((name := label.get("name")), str)
            and name.startswith(self.legacy_label_prefix)
            and name.removeprefix(self.legacy_label_prefix) in finding_ids
        }

    def _remove_legacy_labels(
        self, github: GitHubAPI, number: int, labels: list[dict[str, JsonValue]]
    ) -> None:
        """Remove obsolete per-finding approval labels after state migration."""
        if self.legacy_label_prefix is None:
            return
        for label in labels:
            name = optional_string(label.get("name"))
            if name and name.startswith(self.legacy_label_prefix):
                encoded = urllib.parse.quote(name, safe="")
                github.request("DELETE", f"/issues/{number}/labels/{encoded}")


class QualityCheck[FindingType: ApprovableFinding](ABC):
    """Subject-specific check with a shared, typed execution contract."""

    gate: ClassVar[str]
    report_marker: ClassVar[str]
    approval_lifecycle: ClassVar[ApprovalLifecycle]

    @abstractmethod
    def collect(self, context: CheckContext) -> CheckResult[FindingType]:
        """Collect findings without mutating GitHub state."""

    def report(self, github: GitHubAPI, number: int) -> PullRequestReport:
        """Return the shared report lifecycle configured for this check."""
        if self.report_marker not in REPORTS:
            message = f"Unknown report marker for {type(self).__name__}: {self.report_marker}"
            raise ValueError(message)
        return PullRequestReport.registered(github, number, self.report_marker)

    def sync_approvals(
        self, request: ApprovalRequest, findings: Sequence[FindingType]
    ) -> ApprovalSyncResult:
        """Apply this check's configured approval lifecycle to its findings."""
        return self.approval_lifecycle.sync(request, findings)
