"""Base contract for declarative Quality Graph checks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ci.quality_graph.models import CheckContext, CheckResult, FindingProtocol


class QualityCheck[FindingType: FindingProtocol](ABC):
    """Subject-specific check with a shared, typed execution contract."""

    gate: ClassVar[str]

    @abstractmethod
    def collect(self, context: CheckContext) -> CheckResult[FindingType]:
        """Collect findings without mutating GitHub state."""
