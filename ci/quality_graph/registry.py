"""Register Quality Graph checks and run their direct command handlers."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from monori.ci.quality_graph.base import QualityCheckDefinition


class CommandHandler(Protocol):
    """Describe a check module entry point that processes the current event."""

    def __call__(self) -> int:
        """Process the event and return the check exit code."""
        ...


@dataclass(frozen=True)
class WorkflowJobDefinition:
    """Describe one user-facing check in the pull-request workflow graph."""

    job_id: str
    title: str
    module: str
    gate: str | None = None
    report_marker: str | None = None

    @property
    def summary_anchor(self) -> str:
        """Return the stable Markdown heading anchor for this job summary."""
        return f"quality-graph-{self.job_id}"


WORKFLOW_JOBS = (
    WorkflowJobDefinition("workflow-graph", "Workflow graph validation", "workflow_graph"),
    WorkflowJobDefinition("fmt-check", "Format check", "fmt_check"),
    WorkflowJobDefinition("triple-quotes", "Triple-quoted string style", "triple_quotes"),
    WorkflowJobDefinition(
        "suppressions", "Lint suppression gate", "suppressions", "suppression", "suppression"
    ),
    WorkflowJobDefinition(
        "hardcoded-colors",
        "Hardcoded color gate",
        "hardcoded_colors",
        "color",
        "hardcoded-colors",
    ),
    WorkflowJobDefinition("docs-links", "Documentation links", "docs_links"),
    WorkflowJobDefinition("lint", "Lint", "lint"),
    WorkflowJobDefinition(
        "object-annotations",
        "Python object annotation gate",
        "object_annotations",
        "object",
        "object-annotations",
    ),
    WorkflowJobDefinition(
        "type-casts", "Unsafe type cast gate", "type_casts", "cast", "type-casts"
    ),
    WorkflowJobDefinition("type", "Type check", "type_check"),
    WorkflowJobDefinition("analyze", "Static analysis", "analyze"),
    WorkflowJobDefinition("time-bombs", "Time bomb guardrail", "time_bombs"),
    WorkflowJobDefinition("test-fast", "Fast tests", "test_fast"),
    WorkflowJobDefinition("test-medium", "Medium tests", "test_medium"),
    WorkflowJobDefinition("test-slow", "Slow tests", "test_slow"),
    WorkflowJobDefinition(
        "flaky-tests",
        "Flaky test detection",
        "flaky_tests",
        "flaky",
        "flaky-tests",
    ),
    WorkflowJobDefinition("build", "Build frontend", "build"),
    WorkflowJobDefinition("coverage", "Coverage", "coverage"),
    WorkflowJobDefinition("mutation", "Mutation testing", "mutation", report_marker="mutation"),
    WorkflowJobDefinition(
        "bundle-size", "Frontend bundle size", "bundle_size", "bundle", "bundle-size"
    ),
    WorkflowJobDefinition(
        "frontend-performance",
        "Frontend performance regression",
        "frontend_performance",
        "frontend",
        "frontend-performance",
    ),
    WorkflowJobDefinition("audit", "Dependency and security audit", "audit"),
)
WORKFLOW_JOB_BY_ID = {definition.job_id: definition for definition in WORKFLOW_JOBS}


def workflow_jobs() -> dict[str, WorkflowJobDefinition]:
    """Return user-facing workflow jobs in dashboard display order."""
    return dict(WORKFLOW_JOB_BY_ID)


def workflow_job_for_report(marker: str) -> WorkflowJobDefinition:
    """Return the workflow job that owns a report marker."""
    for definition in WORKFLOW_JOBS:
        if definition.report_marker == marker:
            return definition
    message = f"Unknown Quality Graph report marker: {marker}"
    raise ValueError(message)


def workflow_job_for_gate(gate: str) -> WorkflowJobDefinition:
    """Return the workflow job addressed by one internal command gate."""
    for definition in WORKFLOW_JOBS:
        if definition.gate == gate:
            return definition
    message = f"Unknown Quality Graph gate: {gate}"
    raise ValueError(message)


def workflow_job_module(definition: WorkflowJobDefinition) -> str:
    """Return the import path implementing one registered workflow check."""
    return f"monori.ci.quality_graph.checks.{definition.module}"


@cache
def registered_checks() -> dict[str, type[QualityCheckDefinition]]:
    """Return every Quality Graph check indexed by its command gate."""
    from monori.ci.quality_graph.checks.bundle_size import BundleSizeCheck  # noqa: PLC0415
    from monori.ci.quality_graph.checks.frontend_performance import (  # noqa: PLC0415
        FrontendPerformanceCheck,
    )
    from monori.ci.quality_graph.checks.hardcoded_colors import (  # noqa: PLC0415
        HardcodedColorCheck,
    )
    from monori.ci.quality_graph.checks.object_annotations import (  # noqa: PLC0415
        ObjectAnnotationCheck,
    )
    from monori.ci.quality_graph.checks.suppressions import SuppressionCheck  # noqa: PLC0415

    flaky_check = cast(
        "type[QualityCheckDefinition]",
        importlib.import_module("monori.ci.quality_graph.checks.flaky_tests").FlakyTestCheck,
    )
    type_cast_check: type[QualityCheckDefinition] = importlib.import_module(
        "monori.ci.quality_graph.checks.type_casts"
    ).TypeCastCheck
    checks = (
        ObjectAnnotationCheck,
        type_cast_check,
        SuppressionCheck,
        HardcodedColorCheck,
        BundleSizeCheck,
        FrontendPerformanceCheck,
        flaky_check,
    )
    return {check.definition.gate: check for check in checks if check.definition.gate is not None}


def run_direct_command_checks() -> None:
    """Run checks that apply commands directly from issue-comment events."""
    for check in registered_checks().values():
        if check.pending_marker is not None:
            continue
        module = importlib.import_module(check.__module__)
        handler = cast("CommandHandler", module.main)
        handler()


def main() -> int:
    """Process direct Quality Graph checks for the current GitHub event."""
    run_direct_command_checks()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
