"""
Publish sticky flaky-test findings through the Quality Graph lifecycle.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, override

from monori.ci.lib.annotations import AnnotationLevel, SourceAnnotation
from monori.ci.lib.comments import managed_comment, update_comment_body
from monori.ci.lib.flaky_tests import (
    AttemptResult,
    AttemptStatus,
    CollectedTest,
    Lane,
    PlaywrightRunner,
    PytestRunner,
    RepetitionResult,
    RunnerStack,
    SubprocessExecutor,
    VitestRunner,
    read_manifest,
    repeat_tests,
)
from monori.ci.quality_graph.base import (
    ApprovalLifecycle,
    CheckExecution,
    QualityCheck,
    QualityRuntime,
    ReportCheckRequest,
    read_github_event,
    run_report_check,
)
from monori.ci.quality_graph.job_results import JobResult, JobStatus, without_admin_controls
from monori.ci.quality_graph.models import CheckContext, CheckResult, Metric, Verdict
from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.reporting import (
    RenderedCheckReport,
    ReportFinding,
    ReportModel,
    ReportStatus,
    admin_commands,
    finding_location,
    render_report,
)
from monori.common import JsonValue, integer_value, object_value, optional_string, string_value

if TYPE_CHECKING:
    from collections.abc import Iterable

    from monori.ci.lib.github import GitHubAPI

FINDING_ID_PREFIX = "flaky-"
STATUS_LABEL = "monori-flaky-test-failed"
APPROVAL_STATE_RE = re.compile(r"<!-- monori-flaky-test-approvals: ([0-9a-f,]*) -->")
PENDING_STATE_RE = re.compile(r"<!-- monori-flaky-test-pending: (\d+)(?: ([A-Za-z0-9_-]+))? -->")
EVIDENCE_RE = re.compile(r"<!-- monori-qg-sticky: flaky-tests ([0-9a-f]{40}) ([A-Za-z0-9_-]*) -->")
EVIDENCE_OUTPUT_LIMIT = 500
APPROVALS = ApprovalLifecycle(
    "flaky",
    FINDING_ID_PREFIX,
    APPROVAL_STATE_RE,
    "<!-- monori-flaky-test-approvals: {ids} -->",
    PENDING_STATE_RE,
    allow_file_commands=True,
)


@dataclass(frozen=True)
class FlakyFinding:
    """
    Carry one unstable test and the run that proved it.
    """

    execution: RepetitionResult
    run_url: str

    @property
    def path(self) -> str:
        """
        Return the source path used by approvals and annotations.
        """
        return self.execution.test.path

    @property
    def finding_id(self) -> str:
        """
        Return the stable raw finding fingerprint.
        """
        return self.execution.test.finding_id

    @property
    def failed_attempts(self) -> tuple[AttemptResult, ...]:
        """
        Return every non-passing attempt.
        """
        return tuple(
            attempt
            for attempt in self.execution.attempts
            if attempt.status is not AttemptStatus.PASSED
        )


class FlakyTestCheck(QualityCheck[FlakyFinding]):
    """
    Apply approvals and publication policy to flaky-test evidence.
    """

    definition = WORKFLOW_JOB_BY_ID["flaky-tests"]
    approval_lifecycle = APPROVALS
    supports_ignore_file = True
    pending_marker: ClassVar[str | None] = "monori-flaky-test-pending"
    failure_label: ClassVar[str | None] = STATUS_LABEL

    @override
    def collect(self, context: CheckContext) -> CheckResult[FlakyFinding]:
        """
        Satisfy the shared check contract; collection is runner-driven.
        """
        return CheckResult((), Verdict.PASS)


def display_finding_id(finding_id: str) -> str:
    """
    Prefix a raw fingerprint for administrator commands.
    """
    return f"{FINDING_ID_PREFIX}{finding_id}"


def encode_evidence(head_sha: str, findings: Iterable[FlakyFinding]) -> str:
    """
    Encode bounded sticky evidence in a dashboard comment marker.
    """
    payload = json.dumps(
        [_finding_json(finding) for finding in findings],
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"<!-- monori-qg-sticky: flaky-tests {head_sha} {encoded} -->"


def decode_evidence(body: str) -> tuple[str | None, tuple[FlakyFinding, ...]]:
    """
    Decode sticky evidence from a dashboard comment.
    """
    match = EVIDENCE_RE.search(body)
    if match is None:
        return None, ()
    encoded = match.group(2)
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        value = json.loads(payload)
        if not isinstance(value, list):
            return None, ()
        return match.group(1), tuple(_finding_from_json(item) for item in value)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None, ()


def merge_sticky_findings(
    body: str,
    head_sha: str,
    current: Iterable[FlakyFinding],
) -> tuple[FlakyFinding, ...]:
    """
    Keep prior evidence on the same head and clear it on a new head.
    """
    stored_head, stored = decode_evidence(body)
    merged = {finding.finding_id: finding for finding in stored if stored_head == head_sha}
    merged.update({finding.finding_id: finding for finding in current})
    return tuple(sorted(merged.values(), key=_finding_key))


def persist_evidence(
    github: GitHubAPI,
    comment_id: int,
    body: str,
    head_sha: str,
    findings: Iterable[FlakyFinding],
) -> str:
    """
    Persist current-head evidence without disturbing other PR state.
    """
    marker = encode_evidence(head_sha, findings)
    updated = EVIDENCE_RE.sub(marker, body)
    if updated == body:
        updated = f"{body.rstrip()}\n\n{marker}" if body.strip() else marker
    if updated != body:
        update_comment_body(github, comment_id, updated)
    return updated


def summary_body(
    findings: tuple[FlakyFinding, ...],
    approved: set[str],
    pr_url: str,
    executions: tuple[RepetitionResult, ...] = (),
) -> RenderedCheckReport:
    """
    Render detailed attempt evidence and administrator controls.
    """
    active = [finding for finding in findings if finding.finding_id not in approved]
    current = executions or tuple(finding.execution for finding in findings)
    attempts = [attempt for execution in current for attempt in execution.attempts]
    content = "\n\n".join(_finding_details(finding) for finding in findings)
    return render_report(
        ReportModel(
            "flaky-tests",
            ReportStatus.FAILED if active else ReportStatus.PASSED,
            message=(
                "No newly added frontend or backend tests."
                if not current
                else "Every newly added test passed all isolated repetitions."
                if not findings
                else "A non-passing repetition makes a newly added test unsafe to merge."
            ),
            metrics=(
                Metric("New tests", str(len(current))),
                Metric("Attempts", str(len(attempts))),
                Metric(
                    "Passed",
                    str(sum(attempt.status is AttemptStatus.PASSED for attempt in attempts)),
                ),
                Metric(
                    "Failed",
                    str(sum(attempt.status is AttemptStatus.FAILED for attempt in attempts)),
                ),
                Metric(
                    "Timed out",
                    str(sum(attempt.status is AttemptStatus.TIMED_OUT for attempt in attempts)),
                ),
                Metric(
                    "Runner errors",
                    str(sum(attempt.status is AttemptStatus.RUNNER_ERROR for attempt in attempts)),
                ),
                Metric("Active findings", str(len(active))),
                Metric("Approved", str(len(findings) - len(active))),
            ),
            content=content,
            findings=tuple(
                ReportFinding(
                    f"`{finding.execution.test.name}` · `{display_finding_id(finding.finding_id)}`",
                    approved=finding.finding_id in approved,
                    location=finding_location(pr_url, finding.path, finding.execution.test.line),
                )
                for finding in findings
            ),
            admin=admin_commands(
                "flaky",
                [display_finding_id(finding.finding_id) for finding in active],
                [
                    display_finding_id(finding.finding_id)
                    for finding in findings
                    if finding.finding_id in approved
                ],
                {
                    path: [
                        display_finding_id(finding.finding_id)
                        for finding in active
                        if finding.path == path
                    ]
                    for path in {finding.path for finding in active}
                },
            ),
        )
    )


def source_annotation(finding: FlakyFinding) -> SourceAnnotation:
    """
    Build one lint-style annotation for an unstable added test.
    """
    test = finding.execution.test
    failures = ", ".join(str(attempt.number) for attempt in finding.failed_attempts)
    return SourceAnnotation(
        test.path,
        test.line,
        test.line,
        f"{test.name} was non-passing in attempts {failures}",
        AnnotationLevel.FAILURE,
        title="Flaky test detected",
    )


def _finding_key(finding: FlakyFinding) -> tuple[str, int, str]:
    test = finding.execution.test
    return test.path, test.line, test.runner_id


def _finding_json(finding: FlakyFinding) -> dict[str, JsonValue]:
    test = finding.execution.test
    return {
        "stack": test.stack.value,
        "lane": test.lane.value,
        "path": test.path,
        "line": test.line,
        "runnerId": test.runner_id,
        "name": test.name,
        "runUrl": finding.run_url,
        "attempts": [
            {
                "number": attempt.number,
                "status": attempt.status.value,
                "duration": round(attempt.duration_seconds, 3),
                "output": (
                    attempt.output[:EVIDENCE_OUTPUT_LIMIT]
                    if attempt.status is not AttemptStatus.PASSED
                    else ""
                ),
            }
            for attempt in finding.execution.attempts
        ],
    }


def _finding_from_json(value: JsonValue) -> FlakyFinding:
    if not isinstance(value, dict):
        message = "Flaky-test evidence item must be an object"
        raise TypeError(message)
    test = CollectedTest(
        RunnerStack(str(value["stack"])),
        Lane(str(value["lane"])),
        str(value["path"]),
        int(str(value["line"])),
        str(value["runnerId"]),
        str(value["name"]),
    )
    raw_attempts = value.get("attempts")
    if not isinstance(raw_attempts, list):
        message = "Flaky-test evidence attempts must be an array"
        raise TypeError(message)
    attempts = tuple(
        AttemptResult(
            int(str(item["number"])),
            AttemptStatus(str(item["status"])),
            float(str(item["duration"])),
            str(item.get("output", "")),
        )
        for item in raw_attempts
        if isinstance(item, dict)
    )
    return FlakyFinding(RepetitionResult(test, attempts), str(value.get("runUrl", "")))


def _finding_details(finding: FlakyFinding) -> str:
    test = finding.execution.test
    rows = "\n".join(
        f"| {attempt.number} | {attempt.status.value} | {attempt.duration_seconds:.3f}s |"
        for attempt in finding.execution.attempts
    )
    failures = "\n\n".join(
        f"**Attempt {attempt.number} — {attempt.status.value}**\n\n"
        f"{_code_block(attempt.output or 'No output')}"
        for attempt in finding.failed_attempts
    )
    return (
        f"### `{test.name}`\n\n"
        f"`{test.path}:{test.line}` · `{test.stack.value}` · `{test.lane.value}` · "
        f"[original evidence]({finding.run_url})\n\n"
        "| Attempt | Status | Duration |\n| ---: | --- | ---: |\n"
        f"{rows}\n\n{failures}"
    )


def _code_block(value: str) -> str:
    longest = max((len(match.group()) for match in re.finditer(r"`+", value)), default=2)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{value}\n{fence}"


def execute_manifest(path: Path) -> tuple[RepetitionResult, ...]:
    """
    Run every discovered test through its native isolated adapter.
    """
    executor = SubprocessExecutor()
    runners = {
        RunnerStack.PYTEST: PytestRunner(executor),
        RunnerStack.VITEST: VitestRunner(executor),
        RunnerStack.PLAYWRIGHT: PlaywrightRunner(executor),
    }
    return repeat_tests(read_manifest(path), runners)


def _execution(
    findings: tuple[FlakyFinding, ...],
    executions: tuple[RepetitionResult, ...],
    approved: set[str],
    pull_url: str,
) -> CheckExecution:
    active = tuple(finding for finding in findings if finding.finding_id not in approved)
    report = summary_body(findings, approved, pull_url, executions)
    attempts = tuple(attempt for execution in executions for attempt in execution.attempts)
    return CheckExecution(
        JobStatus.FAILED if active else JobStatus.PASSED,
        without_admin_controls(report.summary),
        (
            Metric("New tests", str(len(executions))),
            Metric("Attempts", str(len(attempts))),
            Metric("Active findings", str(len(active))),
        ),
        report.controls,
        report.control_notes,
        tuple(source_annotation(finding) for finding in active),
    )


def run_check(manifest: Path, runtime: QualityRuntime) -> int:
    """
    Execute the manifest, merge sticky evidence, and publish one job result.
    """
    event = read_github_event()
    event_pull = object_value(event.get("pull_request"), "pull request event")
    number = integer_value(event_pull.get("number"), "pull request number")
    event_head = object_value(event_pull.get("head"), "event pull request head")
    event_head_sha = string_value(event_head.get("sha"), "event head sha")
    initial_pull = object_value(runtime.github.request("GET", f"/pulls/{number}"), "pull request")
    initial_head = object_value(initial_pull.get("head"), "pull request head")
    if string_value(initial_head.get("sha"), "initial head sha") != event_head_sha:
        return _publish_stale(runtime, event_head_sha)
    executions = execute_manifest(manifest)
    pull = object_value(runtime.github.request("GET", f"/pulls/{number}"), "pull request")
    head = object_value(pull.get("head"), "post-execution pull request head")
    if string_value(head.get("sha"), "post-execution head sha") != event_head_sha:
        return _publish_stale(runtime, event_head_sha)
    pull_url = optional_string(pull.get("html_url")) or ""
    run_url = os.environ.get("RUN_URL", "")
    current = tuple(
        FlakyFinding(execution, run_url) for execution in executions if execution.unstable
    )
    dashboard = managed_comment(runtime.github, number, "quality-graph")
    evidence_body = optional_string(dashboard.get("body")) if dashboard is not None else None
    findings = merge_sticky_findings(evidence_body or "", event_head_sha, current)
    if not runtime.read_only:
        if dashboard is None:
            message = "Cannot persist flaky-test evidence without the Quality Graph dashboard"
            raise RuntimeError(message)
        comment_id = integer_value(dashboard.get("id"), "dashboard comment id")
        persist_evidence(runtime.github, comment_id, evidence_body or "", event_head_sha, findings)
    check = FlakyTestCheck()
    return run_report_check(
        check,
        ReportCheckRequest(
            runtime.github,
            number,
            findings,
            runtime.publisher,
            runtime.read_only,
        ),
        lambda approved: _execution(findings, executions, approved, pull_url),
    )


def _publish_stale(runtime: QualityRuntime, event_head_sha: str) -> int:
    runtime.publisher.publish(
        JobResult(
            FlakyTestCheck.definition.job_id,
            FlakyTestCheck.definition.title,
            JobStatus.SKIPPED,
            f"Skipped stale workflow for head `{event_head_sha}`.",
            (Metric("New tests", "0"), Metric("Attempts", "0")),
        )
    )
    return 0


def main() -> int:
    """
    Run the standalone flaky-test Quality Graph check.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    return run_check(args.manifest, QualityRuntime.from_environment())


if __name__ == "__main__":
    raise SystemExit(main())
