# Copyright (c) 2026
"""Protect mutation scoring boundaries and the operator-facing result summary."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from monori.ci.lib import mutation_gate

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("payload", "threshold", "expected"),
    [
        pytest.param({"killed": 4, "survived": 1}, "80", 0, id="inclusive-threshold"),
        pytest.param({"killed": 2, "survived": 1}, "66.7", 1, id="fractional-threshold"),
        pytest.param({"killed": 1}, "100", 0, id="omitted-statuses-default-to-zero"),
        pytest.param({"survived": 1}, "1", 1, id="no-kills"),
        pytest.param({"killed": 4, "timeout": 1}, "90", 1, id="timeouts-in-denominator"),
        pytest.param({"killed": 4, "suspicious": 1}, "90", 1, id="suspicious-in-denominator"),
        pytest.param({"timeout": 1}, "0", 0, id="timeout-is-a-tested-mutant"),
        pytest.param({"suspicious": 1}, "0", 0, id="suspicious-is-a-tested-mutant"),
        pytest.param({}, "0", 2, id="empty-stats-cannot-pass-even-at-zero"),
        pytest.param(
            {
                "total": 20,
                "no_tests": 8,
                "skipped": 6,
                "segfault": 4,
                "check_was_interrupted_by_user": 2,
            },
            "0",
            2,
            id="excluded-results-cannot-be-scored",
        ),
    ],
)
def test_scoring_boundaries_and_status_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, int],
    threshold: str,
    expected: int,
) -> None:
    """Count every tested status, but never count untested results as tested."""
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps(payload))
    monkeypatch.setattr("sys.argv", ["mutation-gate", str(stats), threshold])

    assert mutation_gate.main() == expected


@pytest.mark.parametrize("verdict", [("80", "PASS", 0), ("81", "FAIL", 1)])
@pytest.mark.parametrize("include_totals", [False, True])
def test_summary_explains_score_and_excluded_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    verdict: tuple[str, str, int],
    *,
    include_totals: bool,
) -> None:
    """Report actual counts and verdict without diluting the gate with excluded results."""
    threshold, status, expected = verdict
    payload = {"killed": "80", "survived": "10", "timeout": "6", "suspicious": "4"}
    if include_totals:
        payload.update(
            total="130",
            no_tests="11",
            skipped="8",
            segfault="7",
            check_was_interrupted_by_user="4",
        )
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps(payload))
    monkeypatch.setattr("sys.argv", ["mutation-gate", str(stats), threshold])

    with caplog.at_level(logging.INFO, logger=mutation_gate.__name__):
        assert mutation_gate.main() == expected

    messages = [" ".join(record.getMessage().split()) for record in caplog.records]
    assert "killed 80 yes" in messages
    assert "survived 10 yes" in messages
    assert "timeout 6 yes" in messages
    assert "suspicious 4 yes" in messages
    assert f"no tests {11 if include_totals else 0} no" in messages
    assert f"skipped {8 if include_totals else 0} no" in messages
    assert f"segfault {7 if include_totals else 0} no" in messages
    assert f"interrupted {4 if include_totals else 0} no" in messages
    assert "gate total 100 killed + survived + timeout + suspicious" in messages
    assert f"all results {130 if include_totals else 100}" in messages
    assert (
        f"mutation-gate [{status}]: score 80.00% (killed 80/100, threshold {threshold}%)"
        in messages
    )


@pytest.mark.parametrize("failure", ["usage", "missing-file", "empty-results"])
def test_unscorable_runs_explain_the_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    """Tell operators whether invocation, stats availability, or missing tests blocked scoring."""
    stats = tmp_path / "stats.json"
    if failure == "empty-results":
        stats.write_text("{}")
    arguments, message = {
        "usage": (
            ["mutation-gate"],
            "usage: mutation-gate.py <cicd-stats.json> <threshold>",
        ),
        "missing-file": (
            ["mutation-gate", str(stats), "80"],
            f"mutation-gate: stats file not found: {stats}",
        ),
        "empty-results": (
            ["mutation-gate", str(stats), "80"],
            "mutation-gate: no mutants were tested — nothing to score",
        ),
    }[failure]
    monkeypatch.setattr("sys.argv", arguments)

    assert mutation_gate.main() == 2
    assert (mutation_gate.__name__, logging.ERROR, message) in caplog.record_tuples


def test_standalone_logging_emits_the_score_without_external_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI must display its result even when no caller configured INFO logging."""
    stats = tmp_path / "stats.json"
    stats.write_text('{"killed": 1}')
    monkeypatch.setattr("sys.argv", ["mutation-gate", str(stats), "100"])
    monkeypatch.setattr(logging.root, "handlers", [])
    monkeypatch.setattr(logging.root, "level", logging.WARNING)

    assert mutation_gate.main() == 0
    assert (
        "mutation-gate [PASS]: score 100.00% (killed 1/1, threshold 100%)"
        in capsys.readouterr().err.splitlines()
    )
