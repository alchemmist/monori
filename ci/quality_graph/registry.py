"""Register Quality Graph checks and run their direct command handlers."""

from __future__ import annotations

import importlib
from functools import cache
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from monori.ci.quality_graph.base import QualityCheckDefinition


class CommandHandler(Protocol):
    """Describe a check module entry point that processes the current event."""

    def __call__(self) -> int:
        """Process the event and return the check exit code."""
        ...


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
