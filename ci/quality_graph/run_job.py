"""Execute one Quality Graph command and publish its portable result."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import anyio

from monori.ci.lib.annotations import publish_workflow_annotations
from monori.ci.quality_graph.job_report import build_result
from monori.ci.quality_graph.job_results import JobResultPublisher

if TYPE_CHECKING:
    from monori.ci.quality_graph.registry import WorkflowJobDefinition

TARGET_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


@dataclass(frozen=True)
class CommandResult:
    """Capture one child command's exit status and combined output."""

    returncode: int
    output: str


class CommandRunner(Protocol):
    """Execute trusted argv without a shell."""

    def run(self, command: tuple[str, ...]) -> CommandResult:
        """Run one command and return its complete captured output."""
        ...


class SubprocessCommandRunner:
    """Execute commands through the operating system without shell expansion."""

    def run(self, command: tuple[str, ...]) -> CommandResult:
        """Run a validated command and combine stdout with stderr."""
        return anyio.run(self._run, command)

    async def _run(self, command: tuple[str, ...]) -> CommandResult:
        completed = await anyio.run_process(command, check=False)
        output = (completed.stdout + completed.stderr).decode()
        return CommandResult(completed.returncode, output)


@dataclass(frozen=True)
class RunJobRequest:
    """Describe one make target and every explicit publication sink."""

    check_id: str
    title: str
    make_target: str
    log_path: Path
    result_path: Path
    summary_path: Path
    github_output_path: Path
    diff_path: Path
    fix_target: str = ""


@dataclass(frozen=True)
class MakeCheck:
    """Describe a Quality Graph check implemented by one Make target."""

    definition: WorkflowJobDefinition
    make_target: str
    fix_target: str = ""

    def main(self) -> int:
        """Parse publication paths and run this check through the shared lifecycle."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--log", type=Path, required=True)
        parser.add_argument("--diff", type=Path, required=True)
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--summary", type=Path, required=True)
        parser.add_argument(
            "--github-output",
            type=Path,
            default=Path(os.environ.get("GITHUB_OUTPUT", "github-output.txt")),
        )
        args = parser.parse_args()
        return execute_job(
            RunJobRequest(
                self.definition.job_id,
                self.definition.title,
                self.make_target,
                args.log,
                args.output,
                args.summary,
                args.github_output,
                args.diff,
                self.fix_target,
            ),
            SubprocessCommandRunner(),
        )


def validated_target(target: str) -> str:
    """Return a safe make target or reject shell-like input."""
    if not TARGET_RE.fullmatch(target):
        message = f"Invalid make target: {target}"
        raise ValueError(message)
    return target


def execute_job(request: RunJobRequest, runner: CommandRunner) -> int:
    """Run, diagnose, and publish one job while preserving its command verdict."""
    command = runner.run(("make", validated_target(request.make_target)))
    request.log_path.parent.mkdir(parents=True, exist_ok=True)
    request.log_path.write_text(command.output)
    sys.stdout.write(command.output)
    diff = ""
    if command.returncode != 0 and request.fix_target:
        runner.run(("make", validated_target(request.fix_target)))
        diff_result = runner.run(("git", "diff", "--unified=0", "--no-ext-diff"))
        diff = diff_result.output
        request.diff_path.parent.mkdir(parents=True, exist_ok=True)
        request.diff_path.write_text(diff)
    result = build_result(
        request.check_id,
        request.title,
        command.returncode,
        command.output,
        diff,
    )
    JobResultPublisher(request.result_path, request.summary_path).publish(result)
    publish_workflow_annotations(
        result.annotations,
        omitted_message="Additional source diagnostics are available in the Job Summary.",
    )
    with request.github_output_path.open("a") as github_output:
        github_output.write(f"exit_code={command.returncode}\n")
    return 0
