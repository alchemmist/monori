"""Execute the flaky-test manifest produced by Monori discovery."""

from pathlib import Path

from monori.ci.lib.flaky_tests import (
    PlaywrightRunner,
    PytestRunner,
    RepetitionResult,
    RunnerStack,
    SubprocessExecutor,
    VitestRunner,
    read_manifest,
    repeat_tests,
)


def execute_manifest(path: Path) -> tuple[RepetitionResult, ...]:
    """Run every discovered test through its native isolated adapter."""
    executor = SubprocessExecutor()
    runners = {
        RunnerStack.PYTEST: PytestRunner(executor),
        RunnerStack.VITEST: VitestRunner(executor),
        RunnerStack.PLAYWRIGHT: PlaywrightRunner(executor),
    }
    return repeat_tests(read_manifest(path), runners)
