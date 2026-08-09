"""Test the shared approval and gate-state lifecycle."""

import re
from dataclasses import dataclass
from typing import override

import pytest

from monori.ci.quality_graph.base import (
    ApprovalLifecycle,
    QualityCheck,
)
from monori.ci.quality_graph.checks.bundle_size import BundleFinding, BundleSizeCheck
from monori.ci.quality_graph.commands import parse_command
from monori.ci.quality_graph.models import CheckContext, CheckResult, Verdict
from monori.ci.quality_graph.registry import registered_checks


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
    "example",
    "example-",
    re.compile(r"<!-- pending-approvals: ([a-z0-9,-]*) -->"),
    "<!-- pending-approvals: {ids} -->",
    re.compile(r"<!-- example-pending: (\d+)(?: ([A-Za-z0-9_-]+))? -->"),
)


def test_all_approval_gates_use_the_quality_check_contract() -> None:
    """Require every approvable gate to use the shared QualityCheck lifecycle."""
    checks = registered_checks()

    assert set(checks) == {"bundle", "frontend", "object", "suppression"}
    assert all(issubclass(check, QualityCheck) for check in checks.values())
    assert {gate for gate, check in checks.items() if check.supports_ignore_file} == {
        "object",
        "suppression",
    }
    assert {gate for gate, check in checks.items() if check.pending_marker is not None} == {
        "bundle",
        "frontend",
    }


def test_check_metadata_rejects_a_command_surface_report_marker() -> None:
    """Fail while defining a check whose report marker is not a check report."""
    with pytest.raises(TypeError, match="Unknown check report marker"):

        class InvalidCheck(QualityCheck[Finding]):
            gate = "example"
            report_marker = "quality-graph"
            approval_lifecycle = LIFECYCLE

            @override
            def collect(self, context: CheckContext) -> CheckResult[Finding]:
                findings = tuple(Finding(path, path) for path in context.files)
                return CheckResult(findings, Verdict.PASS)


def test_check_metadata_rejects_lifecycle_capability_mismatches() -> None:
    """Reject gate, file-command, and pending-marker metadata mismatches."""
    with pytest.raises(TypeError, match="gate does not match"):

        class InvalidGate(QualityCheck[Finding]):
            gate = "other"
            report_marker = "bundle-size"
            approval_lifecycle = LIFECYCLE

            @override
            def collect(self, context: CheckContext) -> CheckResult[Finding]:
                return CheckResult((), Verdict.PASS)

    with pytest.raises(TypeError, match="ignore-file metadata"):

        class InvalidFileCapability(QualityCheck[Finding]):
            gate = "example"
            report_marker = "bundle-size"
            approval_lifecycle = LIFECYCLE
            supports_ignore_file = True

            @override
            def collect(self, context: CheckContext) -> CheckResult[Finding]:
                return CheckResult((), Verdict.PASS)

    with pytest.raises(TypeError, match="pending-marker metadata"):

        class InvalidPendingCapability(QualityCheck[Finding]):
            gate = "example"
            report_marker = "bundle-size"
            approval_lifecycle = PENDING_LIFECYCLE

            @override
            def collect(self, context: CheckContext) -> CheckResult[Finding]:
                return CheckResult((), Verdict.PASS)


def test_declarative_report_lifecycle_filters_ids_and_disables_file_commands() -> None:
    """Honor report-check capabilities without gate-specific command code."""
    findings = [Finding("web/dist/app.js", "bundle-size")]
    mixed_command = parse_command("/qg ignore bundle-size,object-other")
    file_command = parse_command("/qg ignore-file web/dist/app.js")
    assert mixed_command is not None
    assert file_command is not None

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
