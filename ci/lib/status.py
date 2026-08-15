"""Define shared visual statuses for CI reports and dashboards."""

from enum import StrEnum


class QualityStatus(StrEnum):
    """Represent a CI result with its human-readable label and icon."""

    WAITING = "wait"
    IN_PROGRESS = "in progress"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"

    @property
    def emoji(self) -> str:
        """Return the canonical icon for the status."""
        return {
            QualityStatus.WAITING: "⏳",
            QualityStatus.IN_PROGRESS: "🚀",
            QualityStatus.PASSED: "✅",
            QualityStatus.FAILED: "❌",
            QualityStatus.SKIPPED: "⏭️",
        }[self]

    @property
    def label(self) -> str:
        """Return the status label prefixed with its canonical icon."""
        return f"{self.emoji} {self.value}"
