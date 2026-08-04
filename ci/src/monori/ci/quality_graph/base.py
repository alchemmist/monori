"""Base contract for declarative Quality Graph checks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from monori.ci.quality_graph.models import CheckContext, CheckResult, FindingProtocol
from monori.ci.quality_graph.reporting import REPORTS, PullRequestReport

if TYPE_CHECKING:
    from monori.ci.lib.github import GitHubAPI


class QualityCheck[FindingType: FindingProtocol](ABC):
    """Subject-specific check with a shared, typed execution contract."""

    gate: ClassVar[str]
    report_marker: ClassVar[str]

    @abstractmethod
    def collect(self, context: CheckContext) -> CheckResult[FindingType]:
        """Collect findings without mutating GitHub state."""

    def report(self, github: GitHubAPI, number: int) -> PullRequestReport:
        """Return the shared report lifecycle configured for this check."""
        if self.report_marker not in REPORTS:
            message = f"Unknown report marker for {type(self).__name__}: {self.report_marker}"
            raise ValueError(message)
        return PullRequestReport.registered(github, number, self.report_marker)
