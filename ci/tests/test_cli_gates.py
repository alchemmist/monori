"""Exercise standalone CI gates through their real process interfaces."""

from __future__ import annotations

import io
import json
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest

from monori.ci.lib import mutation_gate, npm_audit_gate

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@contextmanager
def process_io(arguments: list[str], stdin: str = "") -> Iterator[None]:
    """Temporarily configure command arguments and standard input."""
    previous_arguments = sys.argv
    previous_stdin = sys.stdin
    sys.argv = arguments
    sys.stdin = io.StringIO(stdin)
    try:
        yield
    finally:
        sys.argv = previous_arguments
        sys.stdin = previous_stdin


@pytest.mark.parametrize(
    ("payload", "threshold", "expected"),
    [
        ({"killed": 9, "survived": 1}, "80", 0),
        ({"killed": 1, "survived": 1}, "80", 1),
        ({"killed": 0, "survived": 0}, "80", 2),
    ],
)
def test_mutation_gate_scores_real_stats_file(
    tmp_path: Path, payload: dict[str, int], threshold: str, expected: int
) -> None:
    """Score passing, failing, and empty mutation result sets."""
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps(payload))

    with process_io(["mutation-gate", str(stats), threshold]):
        assert mutation_gate.main() == expected


def test_mutation_gate_rejects_invalid_invocation_and_missing_file(tmp_path: Path) -> None:
    """Reject malformed CLI arguments and an absent stats file."""
    with process_io(["mutation-gate"]):
        assert mutation_gate.main() == 2
    missing = tmp_path / "missing.json"
    with process_io(["mutation-gate", str(missing), "80"]):
        assert mutation_gate.main() == 2


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"vulnerabilities": {}}, 0),
        ({"error": {"code": "EAUDIT", "summary": "failed"}}, 1),
        (
            {
                "vulnerabilities": {
                    "unsafe": {
                        "via": [
                            {
                                "severity": "critical",
                                "url": "https://github.com/advisories/GHSA-unsafe",
                                "title": "Unsafe dependency",
                            }
                        ]
                    }
                }
            },
            1,
        ),
        (
            {
                "vulnerabilities": {
                    "react-router": {
                        "via": [
                            "transitive",
                            {
                                "severity": "high",
                                "url": "https://github.com/advisories/GHSA-qwww-vcr4-c8h2",
                                "title": "Allowed advisory",
                            },
                            {
                                "severity": "low",
                                "url": "https://github.com/advisories/GHSA-low",
                                "title": "Low advisory",
                            },
                        ]
                    }
                }
            },
            0,
        ),
    ],
)
def test_npm_audit_gate_handles_real_audit_payloads(
    payload: dict[str, object], expected: int
) -> None:
    """Accept safe audit data and reject tool or advisory failures."""
    with process_io(["npm-audit-gate"], json.dumps(payload)):
        assert npm_audit_gate.main() == expected


def test_cli_modules_expose_callable_entrypoints() -> None:
    """Keep direct entrypoints available to Make and composite actions."""
    assert callable(mutation_gate.main)
    assert callable(npm_audit_gate.main)
