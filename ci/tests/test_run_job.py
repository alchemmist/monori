"""Test Quality Graph command orchestration through explicit filesystem sinks."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from monori.ci.quality_graph.job_results import JobStatus, read_job_result
from monori.ci.quality_graph.run_job import (
    CommandResult,
    RunJobRequest,
    execute_job,
    validated_target,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class RecordingCommandRunner:
    """Return deterministic command results while recording orchestration order."""

    results: deque[CommandResult]
    commands: list[tuple[str, ...]] = field(default_factory=list)

    def run(self, command: tuple[str, ...]) -> CommandResult:
        """Record one argv and return its configured result."""
        self.commands.append(command)
        return self.results.popleft()


def request(tmp_path: Path, *, fix_target: str = "") -> RunJobRequest:
    """Build one isolated orchestration request."""
    return RunJobRequest(
        "lint",
        "Lint",
        "lint",
        tmp_path / "lint.log",
        tmp_path / "lint.json",
        tmp_path / "summary.md",
        tmp_path / "github-output.txt",
        tmp_path / "lint.diff",
        fix_target,
    )


def test_successful_job_publishes_matching_result_summary_and_output(tmp_path: Path) -> None:
    """Keep command, artifact, summary anchor, and action output on one verdict."""
    runner = RecordingCommandRunner(deque([CommandResult(0, "All checks passed!\n")]))
    job = request(tmp_path)

    assert execute_job(job, runner) == 0

    assert runner.commands == [("make", "lint")]
    assert job.log_path.read_text() == "All checks passed!\n"
    assert read_job_result(job.result_path).status is JobStatus.PASSED
    assert read_job_result(job.result_path).check_id == "lint"
    assert '<a id="quality-graph-lint"></a>' in job.summary_path.read_text()
    assert job.github_output_path.read_text() == "exit_code=0\n"
    assert not job.diff_path.exists()


def test_failed_job_runs_fixer_and_preserves_original_exit_code(tmp_path: Path) -> None:
    """Publish the failing command verdict after producing formatter diagnostics."""
    runner = RecordingCommandRunner(
        deque(
            [
                CommandResult(2, "example.py:3:2: invalid type\n"),
                CommandResult(0, "formatted\n"),
                CommandResult(0, "diff --git a/example.py b/example.py\n"),
            ]
        )
    )
    job = request(tmp_path, fix_target="fmt")

    assert execute_job(job, runner) == 0

    assert runner.commands == [
        ("make", "lint"),
        ("make", "fmt"),
        ("git", "diff", "--unified=0", "--no-ext-diff"),
    ]
    result = read_job_result(job.result_path)
    assert result.status is JobStatus.FAILED
    assert result.annotations[0].path == "example.py"
    assert job.diff_path.read_text().startswith("diff --git")
    assert job.github_output_path.read_text() == "exit_code=2\n"


@pytest.mark.parametrize("target", ["", "lint && deploy", "../lint", "lint target"])
def test_make_target_rejects_shell_syntax(target: str) -> None:
    """Reject targets that cannot be represented as one trusted make argv."""
    with pytest.raises(ValueError, match="Invalid make target"):
        validated_target(target)
