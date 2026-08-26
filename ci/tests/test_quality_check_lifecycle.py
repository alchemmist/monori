"""Test the shared approval and gate-state lifecycle."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

import pytest

from monori.ci.quality_graph.base import (
    ApprovalLifecycle,
    CheckExecution,
    QualityCheck,
    publish_check_execution,
)
from monori.ci.quality_graph.checks.bundle_size import BundleFinding, BundleSizeCheck
from monori.ci.quality_graph.commands import QualityGraphCommand
from monori.ci.quality_graph.job_results import JobResultPublisher, JobStatus, read_job_result
from monori.ci.quality_graph.models import CheckContext, CheckResult, Metric, Verdict
from monori.ci.quality_graph.registry import (
    WORKFLOW_JOB_BY_ID,
    WorkflowJobDefinition,
    registered_checks,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class Finding:
    """Provide a minimal finding accepted by the shared lifecycle."""

    path: str
    finding_id: str


LIFECYCLE = ApprovalLifecycle(
    "example",
    "example-",
    re.compile(r"<!-- example-approvals: ([a-z0-9,-]*) -->"),
    "<!-- example-approvals: {ids} -->",
)

REPORT_LIFECYCLE = ApprovalLifecycle(
    "bundle",
    "bundle-",
    re.compile(r"<!-- report-approvals: ([a-z0-9,-]*) -->"),
    "<!-- report-approvals: {ids} -->",
    allow_file_commands=False,
    finding_ids_include_prefix=True,
)

PENDING_LIFECYCLE = ApprovalLifecycle(
    "bundle",
    "bundle-",
    re.compile(r"<!-- pending-approvals: ([a-z0-9,-]*) -->"),
    "<!-- pending-approvals: {ids} -->",
    re.compile(r"<!-- example-pending: (\d+)(?: ([A-Za-z0-9_-]+))? -->"),
)


def test_all_approval_gates_use_the_quality_check_contract() -> None:
    """Require every approvable gate to use the shared QualityCheck lifecycle."""
    checks = registered_checks()

    assert set(checks) == {
        "bundle",
        "cast",
        "color",
        "flaky",
        "frontend",
        "object",
        "suppression",
    }
    assert all(issubclass(check, QualityCheck) for check in checks.values())
    assert {gate for gate, check in checks.items() if check.supports_ignore_file} == {
        "object",
        "cast",
        "suppression",
        "color",
        "flaky",
    }
    assert {gate for gate, check in checks.items() if check.pending_marker is not None} == {
        "bundle",
        "flaky",
        "frontend",
    }


def test_check_metadata_must_reference_the_workflow_registry() -> None:
    """Reject metadata constructed outside the declarative workflow registry."""
    with pytest.raises(TypeError, match="registered workflow metadata"):

        class InvalidCheck(QualityCheck[Finding]):
            definition = WorkflowJobDefinition("example", "Example", "example", "example")
            approval_lifecycle = LIFECYCLE

            @override
            def collect(self, context: CheckContext) -> CheckResult[Finding]:
                findings = tuple(Finding(path, path) for path in context.files)
                return CheckResult(findings, Verdict.PASS)


def test_check_metadata_rejects_lifecycle_capability_mismatches() -> None:
    """Reject gate, file-command, and pending-marker metadata mismatches."""
    with pytest.raises(TypeError, match="gate does not match"):

        class InvalidGate(QualityCheck[Finding]):
            definition = WORKFLOW_JOB_BY_ID["bundle-size"]
            approval_lifecycle = LIFECYCLE

            @override
            def collect(self, context: CheckContext) -> CheckResult[Finding]:
                return CheckResult((), Verdict.PASS)

    with pytest.raises(TypeError, match="ignore-file metadata"):

        class InvalidFileCapability(QualityCheck[Finding]):
            definition = WORKFLOW_JOB_BY_ID["bundle-size"]
            approval_lifecycle = REPORT_LIFECYCLE
            supports_ignore_file = True

            @override
            def collect(self, context: CheckContext) -> CheckResult[Finding]:
                return CheckResult((), Verdict.PASS)

    with pytest.raises(TypeError, match="pending-marker metadata"):

        class InvalidPendingCapability(QualityCheck[Finding]):
            definition = WORKFLOW_JOB_BY_ID["bundle-size"]
            approval_lifecycle = PENDING_LIFECYCLE

            @override
            def collect(self, context: CheckContext) -> CheckResult[Finding]:
                return CheckResult((), Verdict.PASS)


def test_declarative_report_lifecycle_filters_ids_and_disables_file_commands() -> None:
    """Honor report-check capabilities without gate-specific command code."""
    findings = [Finding("web/dist/app.js", "bundle-size")]
    mixed_command = QualityGraphCommand("ignore", ("bundle-size", "object-other"))
    file_command = QualityGraphCommand("ignore-file", ("web/dist/app.js",))

    assert REPORT_LIFECYCLE.select_findings(mixed_command, findings) == {"bundle-size"}
    assert REPORT_LIFECYCLE.select_findings(file_command, findings) == set()


def test_report_gate_reads_only_approvals_for_current_findings() -> None:
    """Filter persisted approvals against the current report findings."""
    findings = [BundleFinding("bundle-initial-load"), BundleFinding("bundle-other")]

    approved = BundleSizeCheck().read_approvals(
        "<!-- monori-bundle-size-approvals: bundle-initial-load,object-other -->",
        findings,
    )

    assert approved == {"bundle-initial-load"}


@pytest.mark.parametrize(
    ("gate", "finding_id"),
    [
        ("bundle", "bundle-example"),
        ("frontend", "frontend-example"),
        ("object", "object-example"),
        ("cast", "cast-example"),
        ("suppression", "suppression-example"),
        ("color", "color-example"),
        ("flaky", "flaky-example"),
    ],
)
def test_registered_gate_lifecycles_select_their_own_findings(gate: str, finding_id: str) -> None:
    """Apply the same declarative selection contract to every registered gate."""
    check = registered_checks()[gate]
    second_id = f"{gate}-other"
    findings = [Finding("example.py", finding_id), Finding("other.py", second_id)]

    selected = check.approval_lifecycle.select_findings(
        QualityGraphCommand("ignore", (gate,)),
        findings,
    )

    assert selected == {finding_id, second_id}


def test_check_execution_uses_one_publication_policy(tmp_path: Path) -> None:
    """Derive artifact identity, title, and exit code through the shared publisher."""
    result_path = tmp_path / "bundle-size.json"
    execution = CheckExecution(
        JobStatus.FAILED,
        "Bundle regression",
        (Metric("Active", "1"),),
    )

    exit_code = publish_check_execution(
        BundleSizeCheck(),
        JobResultPublisher(result_path),
        execution,
    )

    result = read_job_result(result_path)
    assert exit_code == 1
    assert result.check_id == "bundle-size"
    assert result.title == "Frontend bundle size"
    assert result.status is JobStatus.FAILED
