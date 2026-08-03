"""Typed domain model shared by Quality Graph checks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class FindingProtocol(Protocol):
    @property
    def finding_id(self) -> str: ...


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
