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
    gate: str | None = None

    @property
    def summary_anchor(self) -> str:
        """Return the stable Markdown heading anchor for this job summary."""
        return f"quality-graph-{self.job_id}"


WORKFLOW_JOBS = (
    WorkflowJobDefinition("workflow-graph", "Workflow graph validation"),
    WorkflowJobDefinition("fmt-check", "Format check"),
    WorkflowJobDefinition("suppressions", "Lint suppression gate", "suppression"),
    WorkflowJobDefinition("lint", "Lint"),
    WorkflowJobDefinition("object-annotations", "Python object annotation gate", "object"),
    WorkflowJobDefinition("type", "Type check"),
    WorkflowJobDefinition("analyze", "Static analysis"),
    WorkflowJobDefinition("test-fast", "Fast tests"),
    WorkflowJobDefinition("test-medium", "Medium tests"),
    WorkflowJobDefinition("test-slow", "Slow tests"),
    WorkflowJobDefinition("build", "Build"),
    WorkflowJobDefinition("coverage", "Coverage"),
    WorkflowJobDefinition("mutation", "Mutation testing"),
    WorkflowJobDefinition("bundle-size", "Frontend bundle size", "bundle"),
    WorkflowJobDefinition("frontend-performance", "Frontend performance", "frontend"),
    WorkflowJobDefinition("audit", "Dependency and security audit"),
)


def workflow_jobs() -> dict[str, WorkflowJobDefinition]:
    """Return user-facing workflow jobs in dashboard display order."""
    return {definition.job_id: definition for definition in WORKFLOW_JOBS}


@cache
def registered_checks() -> dict[str, type[QualityCheckDefinition]]:
    """Return every Quality Graph check indexed by its command gate."""
    from monori.ci.quality_graph.checks.bundle_size import BundleSizeCheck  # noqa: PLC0415
    from monori.ci.quality_graph.checks.frontend_performance import (  # noqa: PLC0415
        FrontendPerformanceCheck,
    )
    from monori.ci.quality_graph.checks.object_annotations import (  # noqa: PLC0415
        ObjectAnnotationCheck,
    )
    from monori.ci.quality_graph.checks.suppressions import SuppressionCheck  # noqa: PLC0415

    checks = (
        ObjectAnnotationCheck,
        SuppressionCheck,
        BundleSizeCheck,
        FrontendPerformanceCheck,
    )
    return {check.gate: check for check in checks}


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
