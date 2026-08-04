"""Typed domain model shared by Quality Graph checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping


class Verdict(StrEnum):
    """Overall result category for a quality check."""

    PASS = "pass"
    FAIL = "fail"


class FindingProtocol(Protocol):
    """Common protocol for all quality-gate finding objects."""

    @property
    def finding_id(self) -> str:
        """Identifier to deduplicate and reference findings."""
        ...


@dataclass(frozen=True)
class CheckContext:
    """Pure input for a check, independent of GitHub API transport."""

    files: Mapping[str, str]
    changed_lines: Mapping[str, frozenset[int]]


@dataclass(frozen=True)
class CheckResult[FindingType: FindingProtocol]:
    """Common result shape before approvals are applied."""

    findings: tuple[FindingType, ...]
    verdict: Verdict
