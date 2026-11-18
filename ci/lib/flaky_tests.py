"""
Discover and repeatedly execute newly added product tests.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, override

import anyio

from monori.ci.lib.findings import stable_finding_id

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from monori.common import JsonValue

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
BASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")
REPETITIONS = 10
MAX_ATTEMPT_OUTPUT = 4_000


class RunnerStack(StrEnum):
    """
    Name a supported test runner.
    """

    PYTEST = "pytest"
    VITEST = "vitest"
    PLAYWRIGHT = "playwright"


class Lane(StrEnum):
    """
    Name the regular Quality Graph test lane owning a test.
    """

    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"


LANE_TIMEOUT_SECONDS = {Lane.FAST: 60.0, Lane.MEDIUM: 120.0, Lane.SLOW: 180.0}


class AttemptStatus(StrEnum):
    """
    Classify one isolated runner invocation.
    """

    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed out"
    RUNNER_ERROR = "runner error"


@dataclass(frozen=True)
class CollectedTest:
    """
    Describe one canonical test case reported by its native runner.
    """

    stack: RunnerStack
    lane: Lane
    path: str
    line: int
    runner_id: str
    name: str

    @property
    def finding_id(self) -> str:
        """
        Return a stable identity for approvals and sticky evidence.
        """
        return stable_finding_id(f"{self.stack}:{self.path}:{self.runner_id}")


@dataclass(frozen=True)
class AttemptResult:
    """
    Record one isolated attempt of one canonical test case.
    """

    number: int
    status: AttemptStatus
    duration_seconds: float
    output: str = ""


@dataclass(frozen=True)
class RepetitionResult:
    """
    Group every repetition of one discovered test case.
    """

    test: CollectedTest
    attempts: tuple[AttemptResult, ...]

    @property
    def unstable(self) -> bool:
        """
        Return whether any attempt did not pass.
        """
        return any(attempt.status is not AttemptStatus.PASSED for attempt in self.attempts)


class AttemptRunner(Protocol):
    """
    Execute one canonical test case in an isolated process.
    """

    def run(self, test: CollectedTest, attempt: int) -> AttemptResult:
        """
        Return one typed attempt outcome.
        """
        ...


@dataclass(frozen=True)
class ProcessResult:
    """
    Capture one bounded child-process outcome.
    """

    returncode: int | None
    output: str
    duration_seconds: float
    timed_out: bool = False


class ProcessExecutor(Protocol):
    """
    Execute trusted argv for one runner adapter.
    """

    def run(self, command: tuple[str, ...], cwd: str, timeout_seconds: float) -> ProcessResult:
        """
        Return a bounded process outcome.
        """
        ...


class SubprocessExecutor:
    """
    Execute one attempt without shell expansion.
    """

    def run(self, command: tuple[str, ...], cwd: str, timeout_seconds: float) -> ProcessResult:
        """
        Run one command in a fresh subprocess.
        """
        return anyio.run(self._run, command, cwd, timeout_seconds)

    async def _run(
        self,
        command: tuple[str, ...],
        cwd: str,
        timeout_seconds: float,
    ) -> ProcessResult:
        started = time.monotonic()
        try:
            with anyio.fail_after(timeout_seconds):
                completed = await anyio.run_process(command, cwd=cwd, check=False)
        except TimeoutError:
            return ProcessResult(
                None,
                "Attempt timed out",
                time.monotonic() - started,
                timed_out=True,
            )
        output = (completed.stdout + completed.stderr).decode(errors="replace")
        return ProcessResult(
            completed.returncode,
            output[-MAX_ATTEMPT_OUTPUT:],
            time.monotonic() - started,
        )


@dataclass(frozen=True)
class CommandAttemptRunner:
    """
    Map trusted runner commands into typed attempt outcomes.
    """

    executor: ProcessExecutor

    def command(self, test: CollectedTest) -> tuple[tuple[str, ...], str]:
        """
        Return runner argv and working directory for one case.
        """
        raise NotImplementedError

    def run(self, test: CollectedTest, attempt: int) -> AttemptResult:
        """
        Execute and classify one isolated attempt.
        """
        command, cwd = self.command(test)
        process = self.executor.run(command, cwd, LANE_TIMEOUT_SECONDS[test.lane])
        if process.timed_out:
            status = AttemptStatus.TIMED_OUT
        elif process.returncode == 0:
            status = AttemptStatus.PASSED
        elif process.returncode == 1:
            status = AttemptStatus.FAILED
        else:
            status = AttemptStatus.RUNNER_ERROR
        return AttemptResult(attempt, status, process.duration_seconds, process.output)


class PytestRunner(CommandAttemptRunner):
    """
    Select one pytest node ID.
    """

    @override
    def command(self, test: CollectedTest) -> tuple[tuple[str, ...], str]:
        """
        Build the isolated pytest command.
        """
        return (
            ("uv", "run", "--locked", "--group", "test", "pytest", "-q", test.runner_id),
            ".",
        )


class VitestRunner(CommandAttemptRunner):
    """
    Select one Vitest case by file and full expanded name.
    """

    @override
    def command(self, test: CollectedTest) -> tuple[tuple[str, ...], str]:
        """
        Build the isolated Vitest command with retries disabled.
        """
        return (
            (
                "./node_modules/.bin/vitest",
                "run",
                test.path.removeprefix("web/"),
                "--testNamePattern",
                f"^{re.escape(test.name)}$",
                "--retry=0",
                "--maxWorkers=1",
                "--no-file-parallelism",
            ),
            "web",
        )


class PlaywrightRunner(CommandAttemptRunner):
    """
    Select one Playwright case by definition line and expanded title.
    """

    @override
    def command(self, test: CollectedTest) -> tuple[tuple[str, ...], str]:
        """
        Build the isolated Playwright command with retries disabled.
        """
        title = test.name.rsplit(" > ", 1)[-1]
        return (
            (
                "./node_modules/.bin/playwright",
                "test",
                f"{test.path.removeprefix('web/')}:{test.line}",
                "--grep",
                f"{re.escape(title)}$",
                "--retries=0",
                "--workers=1",
                "--reporter=line",
            ),
            "web",
        )


def eligible_test_path(path: str) -> bool:
    """
    Return whether a repository path contains product tests in scope.
    """
    lowered = path.lower()
    return (
        (lowered.startswith("server/tests/") and lowered.endswith(".py"))
        or (lowered.startswith("web/src/") and lowered.endswith((".test.ts", ".test.tsx")))
        or (lowered.startswith("web/e2e/") and lowered.endswith((".spec.ts", ".spec.tsx")))
    )


def added_test_lines(patch: str) -> dict[str, frozenset[int]]:
    """
    Extract added destination lines for test files in scope.
    """
    path: str | None = None
    line_number: int | None = None
    result: dict[str, set[int]] = {}
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            path = None
            line_number = None
            continue
        if line_number is None and line.startswith("+++ b/"):
            candidate = line[6:]
            path = candidate if eligible_test_path(candidate) else None
            if path is not None:
                result.setdefault(path, set())
            continue
        if match := HUNK_RE.match(line):
            line_number = int(match.group(1))
            continue
        if path is None or line_number is None or line.startswith("\\ No newline"):
            continue
        if line.startswith("+"):
            result[path].add(line_number)
            line_number += 1
        elif not line.startswith("-"):
            line_number += 1
    return {path: frozenset(lines) for path, lines in result.items() if lines}


def select_added_tests(
    collected: Iterable[CollectedTest],
    changed_lines: Mapping[str, frozenset[int]],
) -> tuple[CollectedTest, ...]:
    """
    Select native test cases whose source definition line was added.
    """
    selected = (
        test for test in collected if test.line in changed_lines.get(test.path, frozenset())
    )
    return tuple(
        sorted(selected, key=lambda test: (test.lane, test.path, test.line, test.runner_id))
    )


def repository_path(value: str) -> str:
    """
    Normalize an absolute collected path into a repository-relative path.
    """
    path = Path(value)
    parts = path.parts
    for root in ("server", "web"):
        if root in parts:
            return Path(*parts[parts.index(root) :]).as_posix()
    return path.as_posix().removeprefix("./")


class PytestDefinitionCollector(ast.NodeVisitor):
    """
    Index pytest function definitions by their node-id path.
    """

    def __init__(self) -> None:
        """
        Initialize an empty definition index.
        """
        self.classes: list[str] = []
        self.lines: dict[tuple[str, ...], int] = {}

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """
        Track nested test classes while visiting their methods.
        """
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """
        Record pytest-compatible function and method definitions.
        """
        if node.name.startswith("test_"):
            self.lines[(*self.classes, node.name)] = node.lineno

    @override
    def generic_visit(self, node: ast.AST) -> None:
        """
        Record async tests through the generic visitor dispatch.
        """
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_"):
            self.lines[(*self.classes, node.name)] = node.lineno
        super().generic_visit(node)


def parse_pytest_collection(
    output: str,
    sources: Mapping[str, str],
) -> tuple[CollectedTest, ...]:
    """
    Convert pytest collection node IDs into canonical test cases.
    """
    definitions: dict[str, dict[tuple[str, ...], int]] = {}
    for path, source in sources.items():
        collector = PytestDefinitionCollector()
        collector.visit(ast.parse(source, filename=path))
        definitions[path] = collector.lines
    tests: list[CollectedTest] = []
    for raw in output.splitlines():
        node_id = raw.strip()
        if "::" not in node_id:
            continue
        path, *parts = node_id.split("::")
        function = parts[-1].split("[", 1)[0]
        definition = (*parts[:-1], function)
        line = definitions.get(path, {}).get(definition)
        if line is None:
            continue
        lane = Lane.MEDIUM if "/integration/" in path else Lane.FAST
        tests.append(
            CollectedTest(RunnerStack.PYTEST, lane, path, line, node_id, " > ".join(parts))
        )
    return tuple(tests)


def parse_vitest_collection(payload: str) -> tuple[CollectedTest, ...]:
    """
    Convert Vitest list JSON into canonical test cases.
    """
    raw_items = json.loads(payload)
    if not isinstance(raw_items, list):
        message = "Vitest collection must be a JSON array"
        raise TypeError(message)
    tests: list[CollectedTest] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        file = raw.get("file")
        location = raw.get("location")
        if not isinstance(name, str) or not isinstance(file, str) or not isinstance(location, dict):
            continue
        line = location.get("line")
        if not isinstance(line, int):
            continue
        path = repository_path(file)
        lane = Lane.MEDIUM if path.endswith(".test.tsx") else Lane.FAST
        tests.append(CollectedTest(RunnerStack.VITEST, lane, path, line, name, name))
    return tuple(tests)


def parse_playwright_collection(payload: str) -> tuple[CollectedTest, ...]:
    """
    Convert Playwright list JSON into canonical end-to-end cases.
    """
    data = json.loads(payload)
    if not isinstance(data, dict) or not isinstance(data.get("suites"), list):
        message = "Playwright collection must contain suites"
        raise TypeError(message)
    tests: list[CollectedTest] = []
    for suite in data["suites"]:
        _append_playwright_suite(tests, suite, ())
    return tuple(tests)


def _append_playwright_suite(
    tests: list[CollectedTest],
    value: JsonValue,
    parents: tuple[str, ...],
) -> None:
    if not isinstance(value, dict):
        return
    title = value.get("title")
    current = parents
    if isinstance(title, str) and not title.endswith((".spec.ts", ".spec.tsx")):
        current = (*parents, title)
    specs = value.get("specs", [])
    if isinstance(specs, list):
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            spec_title = spec.get("title")
            case_id = spec.get("id")
            file = spec.get("file")
            line = spec.get("line")
            if (
                not isinstance(spec_title, str)
                or not isinstance(case_id, str)
                or not isinstance(file, str)
                or not isinstance(line, int)
            ):
                continue
            path = f"web/e2e/{file.removeprefix('e2e/')}"
            name = " > ".join((*current, spec_title))
            tests.append(
                CollectedTest(RunnerStack.PLAYWRIGHT, Lane.SLOW, path, line, case_id, name)
            )
    suites = value.get("suites", [])
    if isinstance(suites, list):
        for suite in suites:
            _append_playwright_suite(tests, suite, current)


def repeat_tests(
    tests: Iterable[CollectedTest],
    runners: Mapping[RunnerStack, AttemptRunner],
) -> tuple[RepetitionResult, ...]:
    """
    Execute every selected case exactly ten times in deterministic order.
    """
    return tuple(
        RepetitionResult(
            test,
            tuple(runners[test.stack].run(test, number) for number in range(1, REPETITIONS + 1)),
        )
        for test in tests
    )


def collected_test_json(test: CollectedTest) -> dict[str, JsonValue]:
    """
    Serialize one selected case for the action phase boundary.
    """
    return {
        "stack": test.stack.value,
        "lane": test.lane.value,
        "path": test.path,
        "line": test.line,
        "runnerId": test.runner_id,
        "name": test.name,
    }


def collected_test_from_json(value: JsonValue) -> CollectedTest:
    """
    Deserialize one selected test manifest entry.
    """
    if not isinstance(value, dict):
        message = "Flaky-test manifest entry must be an object"
        raise TypeError(message)
    return CollectedTest(
        RunnerStack(str(value["stack"])),
        Lane(str(value["lane"])),
        str(value["path"]),
        int(str(value["line"])),
        str(value["runnerId"]),
        str(value["name"]),
    )


def write_manifest(path: Path, tests: Iterable[CollectedTest]) -> None:
    """
    Write selected cases in deterministic order.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([collected_test_json(test) for test in tests], indent=2, sort_keys=True) + "\n"
    )


def read_manifest(path: Path) -> tuple[CollectedTest, ...]:
    """
    Read selected cases from the discovery phase.
    """
    value = json.loads(path.read_text())
    if not isinstance(value, list):
        message = "Flaky-test manifest must be an array"
        raise TypeError(message)
    return tuple(collected_test_from_json(item) for item in value)


def validated_base(value: str) -> str:
    """
    Return a safe Git base revision.
    """
    if not BASE_RE.fullmatch(value):
        message = f"Invalid base ref: {value}"
        raise ValueError(message)
    return value


def patch_for_base(base: str, executor: ProcessExecutor) -> str:
    """
    Read the pull-request patch through the shared process seam.
    """
    result = executor.run(
        (
            "git",
            "diff",
            "--unified=0",
            "--no-ext-diff",
            "--diff-filter=ACMR",
            f"{validated_base(base)}...HEAD",
            "--",
        ),
        ".",
        60,
    )
    if result.returncode != 0:
        message = f"Cannot read pull-request diff: {result.output}"
        raise RuntimeError(message)
    return result.output


def discover_repository(base: str, executor: ProcessExecutor) -> tuple[CollectedTest, ...]:
    """
    Collect native runner identities and select definitions added by the diff.
    """
    changed = added_test_lines(patch_for_base(base, executor))
    collected: list[CollectedTest] = []
    pytest_paths = sorted(path for path in changed if path.startswith("server/tests/"))
    if pytest_paths:
        result = executor.run(
            (
                "uv",
                "run",
                "--locked",
                "--group",
                "test",
                "pytest",
                "--collect-only",
                "-q",
                *pytest_paths,
            ),
            ".",
            120,
        )
        _require_collection("pytest", result)
        sources = {path: Path(path).read_text() for path in pytest_paths}
        collected.extend(parse_pytest_collection(result.output, sources))
    vitest_paths = sorted(path for path in changed if path.startswith("web/src/"))
    if vitest_paths:
        result = executor.run(
            (
                "./node_modules/.bin/vitest",
                "list",
                *(path.removeprefix("web/") for path in vitest_paths),
                "--json",
                "--includeTaskLocation",
            ),
            "web",
            120,
        )
        _require_collection("Vitest", result)
        collected.extend(parse_vitest_collection(result.output))
    playwright_paths = sorted(path for path in changed if path.startswith("web/e2e/"))
    if playwright_paths:
        result = executor.run(
            (
                "./node_modules/.bin/playwright",
                "test",
                *(path.removeprefix("web/") for path in playwright_paths),
                "--list",
                "--reporter=json",
                "--retries=0",
            ),
            "web",
            120,
        )
        _require_collection("Playwright", result)
        collected.extend(parse_playwright_collection(result.output))
    selected = select_added_tests(collected, changed)
    _validate_selectors(selected)
    return selected


def _require_collection(name: str, result: ProcessResult) -> None:
    if result.returncode != 0:
        message = f"{name} collection failed: {result.output}"
        raise RuntimeError(message)


def _validate_selectors(tests: Iterable[CollectedTest]) -> None:
    selectors: set[tuple[RunnerStack, str, int, str]] = set()
    for test in tests:
        selector = (test.stack, test.path, test.line, test.name)
        if selector in selectors:
            message = f"Ambiguous expanded test identity: {test.path}:{test.line} {test.name}"
            raise RuntimeError(message)
        selectors.add(selector)


def main() -> int:
    """
    Discover selected tests for the standalone Quality Graph action.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    tests = discover_repository(args.base, SubprocessExecutor())
    write_manifest(args.manifest, tests)
    if args.github_output is not None:
        with args.github_output.open("a") as output:
            output.write(
                f"has_slow={'true' if any(test.lane is Lane.SLOW for test in tests) else 'false'}\n"
            )
            output.write(f"test_count={len(tests)}\n")
    sys.stdout.write(f"Discovered {len(tests)} newly added test cases\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
