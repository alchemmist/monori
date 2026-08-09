"""Base contract for declarative Quality Graph checks."""

from __future__ import annotations

import sys
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Protocol, override

from monori.ci.lib.annotations import (
    SourceAnnotation,
    grouped_annotations,
    workflow_annotation_command,
)
from monori.ci.lib.comments import managed_comment, workflow_bot_logins
from monori.ci.lib.github import is_admin, sync_label
from monori.ci.quality_graph.commands import (
    QualityGraphCommand,
    command_request,
    command_targets_gate,
    decode_command,
    encode_command,
    parse_command,
    validate_command,
)
from monori.ci.quality_graph.job_results import (
    JobMetric,
    JobResult,
    JobResultPublisher,
    JobStatus,
    controls_from_markdown,
    without_admin_controls,
)
from monori.ci.quality_graph.models import CheckContext, CheckResult, FindingProtocol
from monori.ci.quality_graph.reporting import CHECK_REPORTS
from monori.common import JsonValue, object_value, optional_string

if TYPE_CHECKING:
    from collections.abc import Sequence
    from re import Pattern

    from monori.ci.lib.github import GitHubAPI, RepositoryGitHubAPI


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
class PendingApprovalRequest:
    """Bundle the state required to authorize and queue a pending command."""

    github: GitHubAPI
    number: int
    pull_body: str
    command: QualityGraphCommand
    pending_marker: str


@dataclass(frozen=True)
class ApprovalLifecycle:
    """Manage persistent approvals and pending commands for one gate."""

    gate: str
    finding_prefix: str
    state_pattern: Pattern[str]
    state_marker: str
    pending_pattern: Pattern[str] | None = None
    legacy_label_prefix: str | None = None
    allow_file_commands: bool = False
    finding_ids_include_prefix: bool = False

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

    def arm_pending(self, request: PendingApprovalRequest) -> None:
        """Create isolated authorization state and queue a pull-request command."""
        if self.pending_pattern is None:
            message = f"{self.gate} does not support pending commands"
            raise RuntimeError(message)
        encoded = encode_command(request.command)
        authorization = self.authorization_marker(encoded)
        raw_authorization = request.github.request(
            "POST", f"/issues/{request.number}/comments", {"body": authorization}
        )
        authorization_comment = object_value(raw_authorization, "authorization comment")
        authorization_id = authorization_comment.get("id")
        if not isinstance(authorization_id, int):
            message = f"Authorization comment for {self.gate} has no numeric id"
            raise TypeError(message)
        marker = f"<!-- {request.pending_marker}: {authorization_id} {encoded} -->"
        updated_pull = self.pending_pattern.sub(marker, request.pull_body)
        if marker not in updated_pull:
            updated_pull = f"{updated_pull.rstrip()}\n\n{marker}".strip()
        try:
            if updated_pull != request.pull_body:
                request.github.request("PATCH", f"/pulls/{request.number}", {"body": updated_pull})
        except RuntimeError:
            request.github.request("DELETE", f"/issues/comments/{authorization_id}")
            raise

    def consume_pending(self, github: GitHubAPI, body: str) -> None:
        """Delete the isolated authorization after consuming its command."""
        if self.pending_pattern is None or (match := self.pending_pattern.search(body)) is None:
            return
        encoded = match.group(2)
        if encoded is None:
            return
        comment_id = int(match.group(1))
        github.request("DELETE", f"/issues/comments/{comment_id}")

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
        authorized = (
            request.command is not None
            and request.author is not None
            and is_admin(request.github, request.author)
        )
        return self._sync(request, findings, authorized=authorized)

    def sync_pending(
        self,
        github: GitHubAPI,
        number: int,
        body: str,
        findings: Sequence[ApprovableFinding],
        labels: list[dict[str, JsonValue]] | None = None,
    ) -> ApprovalSyncResult:
        """Resolve a bot-authorized pending command and synchronize approvals."""
        command = self.pending_command(github, body)
        effective_body = self.without_pending(body) if command is not None else body
        request = ApprovalRequest(github, number, effective_body, command, None, labels or [])
        result = self._sync(request, findings, authorized=command is not None)
        if command is not None:
            self.consume_pending(github, body)
        return result

    def _sync(
        self,
        request: ApprovalRequest,
        findings: Sequence[ApprovableFinding],
        *,
        authorized: bool,
    ) -> ApprovalSyncResult:
        """Synchronize approvals after the command source has been authorized."""
        finding_ids = {finding.finding_id for finding in findings}
        state_exists = self.state_pattern.search(request.body) is not None
        approved = (
            self.read(request.body)
            if state_exists
            else self._legacy_approvals(request.labels, finding_ids)
        )
        self._remove_legacy_labels(request.github, request.number, request.labels)
        approved &= finding_ids
        changed = False
        if (
            request.command is not None
            and authorized
            and request.command.name not in {"help", "status"}
        ):
            selected = self.select_findings(request.command, findings)
            approved = (
                approved - selected
                if request.command.name == "remove-ignore"
                else approved | selected
            )
            changed = bool(selected)
        if not state_exists or (request.command is not None and authorized):
            self.persist_approvals(request.github, request.number, request.body, approved)
        return ApprovalSyncResult(approved, authorized, changed)

    def select_findings(
        self, command: QualityGraphCommand, findings: Sequence[ApprovableFinding]
    ) -> set[str]:
        """Select findings addressed by a canonical Quality Graph command."""
        all_ids = {finding.finding_id for finding in findings}
        if command.name == "ignore-file":
            if not self.allow_file_commands:
                return set()
            return {finding.finding_id for finding in findings if finding.path in command.arguments}
        if command.name not in {"ignore", "remove-ignore"}:
            return set()
        if self.gate in command.arguments:
            return all_ids
        selected = {
            argument
            if self.finding_ids_include_prefix
            else argument.removeprefix(self.finding_prefix)
            for argument in command.arguments
            if argument.startswith(self.finding_prefix)
        }
        return selected & all_ids

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


class QualityCheckDefinition(ABC):
    """Define registry metadata shared by every Quality Graph check class."""

    gate: ClassVar[str]
    job_id: ClassVar[str]
    report_marker: ClassVar[str]
    approval_lifecycle: ClassVar[ApprovalLifecycle]
    supports_ignore_file: ClassVar[bool] = False
    pending_marker: ClassVar[str | None] = None
    failure_label: ClassVar[str | None] = None

    @override
    def __init_subclass__(cls) -> None:
        """Reject check metadata that disagrees with its approval lifecycle."""
        super().__init_subclass__()
        lifecycle = getattr(cls, "approval_lifecycle", None)
        if lifecycle is None:
            return
        if lifecycle.gate != cls.gate:
            message = f"{cls.__name__} gate does not match its approval lifecycle"
            raise TypeError(message)
        if lifecycle.allow_file_commands != cls.supports_ignore_file:
            message = f"{cls.__name__} ignore-file metadata does not match its lifecycle"
            raise TypeError(message)
        if (lifecycle.pending_pattern is not None) != (cls.pending_marker is not None):
            message = f"{cls.__name__} pending-marker metadata does not match its lifecycle"
            raise TypeError(message)
        if cls.report_marker not in CHECK_REPORTS:
            message = f"Unknown check report marker for {cls.__name__}: {cls.report_marker}"
            raise TypeError(message)

    @classmethod
    def arm_pending(cls, github: GitHubAPI, number: int, command: QualityGraphCommand) -> None:
        """Authorize and queue a pending command through this check's lifecycle."""
        if cls.pending_marker is None:
            message = f"{cls.gate} does not support pending commands"
            raise RuntimeError(message)
        report = managed_comment(github, number, "quality-graph")
        if report is None:
            message = "Cannot authorize command without a Quality Graph dashboard"
            raise RuntimeError(message)
        pull = object_value(github.request("GET", f"/pulls/{number}"), "pull request")
        pull_body = optional_string(pull.get("body")) or ""
        cls.approval_lifecycle.arm_pending(
            PendingApprovalRequest(
                github,
                number,
                pull_body,
                command,
                cls.pending_marker,
            )
        )


class QualityCheck[FindingType: ApprovableFinding](QualityCheckDefinition, ABC):
    """Subject-specific check with a shared, typed execution contract."""

    @abstractmethod
    def collect(self, context: CheckContext) -> CheckResult[FindingType]:
        """Collect findings without mutating GitHub state."""

    def sync_approvals(
        self, request: ApprovalRequest, findings: Sequence[FindingType]
    ) -> ApprovalSyncResult:
        """Apply this check's configured approval lifecycle to its findings."""
        return self.approval_lifecycle.sync(request, findings)

    def sync_pending_approvals(
        self,
        github: GitHubAPI,
        number: int,
        body: str,
        findings: Sequence[FindingType],
        labels: list[dict[str, JsonValue]] | None = None,
    ) -> ApprovalSyncResult:
        """Apply a bot-authorized pending command through the shared lifecycle."""
        return self.approval_lifecycle.sync_pending(github, number, body, findings, labels)


class PullRequestSourceCheck[FindingType: ApprovableFinding](QualityCheck[FindingType], ABC):
    """Run a source-oriented check through the shared pull-request lifecycle."""

    @abstractmethod
    def collect_pull_request(
        self, github: RepositoryGitHubAPI, pull: dict[str, JsonValue]
    ) -> list[FindingType]:
        """Collect findings from the current pull request."""

    @abstractmethod
    def render_summary(
        self, findings: list[FindingType], approved: set[str], pull_request_url: str
    ) -> str:
        """Render the final managed report for this check."""

    @abstractmethod
    def source_annotation(self, finding: FindingType) -> SourceAnnotation:
        """Build one typed source annotation for an active finding."""

    def run_pull_request_gate(
        self,
        github: RepositoryGitHubAPI,
        event: dict[str, JsonValue],
        publisher: JobResultPublisher,
        *,
        read_only: bool = False,
    ) -> int:
        """Execute the shared source-check lifecycle for a pull-request event."""
        number = self._pull_request_number(event)
        if number is None:
            return 0
        return self._run_pull_request_gate(github, event, number, publisher, read_only=read_only)

    def _run_pull_request_gate(
        self,
        github: RepositoryGitHubAPI,
        event: dict[str, JsonValue],
        number: int,
        publisher: JobResultPublisher,
        *,
        read_only: bool,
    ) -> int:
        """Execute a source check and publish its portable job result."""
        raw_pull = github.request("GET", f"/pulls/{number}")
        if raw_pull is None:
            message = f"Pull request #{number} was not found"
            raise RuntimeError(message)
        pull = object_value(raw_pull, "pull request")
        findings = self.collect_pull_request(github, pull)
        request = command_request(event)
        command = parse_command(request.body) if request is not None else None
        if command is not None and (
            validate_command(command) is not None or not command_targets_gate(command, self.gate)
        ):
            command = None
        author = request.login if command is not None and request is not None else None
        body = optional_string(pull.get("body")) or ""
        if read_only:
            approved = self.approval_lifecycle.read(body) & {
                finding.finding_id for finding in findings
            }
        else:
            sync = self.sync_approvals(
                ApprovalRequest(
                    github,
                    number,
                    body,
                    command,
                    author,
                    github.paged(f"/issues/{number}/labels"),
                ),
                findings,
            )
            approved = sync.approved
        active = [finding for finding in findings if finding.finding_id not in approved]
        if self.failure_label is not None and not read_only:
            sync_label(github, number, self.failure_label, present=bool(active))
        pull_request_url = optional_string(pull.get("html_url")) or ""
        summary = self.render_summary(findings, approved, pull_request_url)
        annotations = tuple(self.source_annotation(finding) for finding in active)
        result = JobResult(
            self.job_id,
            CHECK_REPORTS[self.report_marker].title,
            JobStatus.PASSED if not active else JobStatus.FAILED,
            without_admin_controls(summary),
            (
                JobMetric("Findings", str(len(findings))),
                JobMetric("Active", str(len(active))),
            ),
            annotations,
            controls_from_markdown(summary),
        )
        publisher.publish(result)
        for annotation in grouped_annotations(annotations):
            sys.stderr.write(f"{workflow_annotation_command(annotation)}\n")
        if len(annotations) > len(grouped_annotations(annotations)):
            sys.stderr.write("::notice::Additional findings are available in the Job Summary.\n")
        return 1 if active else 0

    @staticmethod
    def _pull_request_number(event: dict[str, JsonValue]) -> int | None:
        """Extract a pull-request number from pull-request or issue events."""
        pull = event.get("pull_request")
        if isinstance(pull, dict):
            number = pull.get("number")
            return number if isinstance(number, int) else None
        issue = event.get("issue")
        if not isinstance(issue, dict) or not issue.get("pull_request"):
            return None
        number = issue.get("number")
        return number if isinstance(number, int) else None
