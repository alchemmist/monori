from __future__ import annotations

import json

import pytest

from monori.ci.lib.flaky_tests import (
    AttemptResult,
    AttemptStatus,
    CollectedTest,
    Lane,
    PlaywrightRunner,
    ProcessResult,
    PytestRunner,
    RunnerStack,
    VitestRunner,
    added_test_lines,
    eligible_test_path,
    parse_playwright_collection,
    parse_pytest_collection,
    parse_vitest_collection,
    repeat_tests,
    repository_path,
    select_added_tests,
)

PATCH = (
    "diff --git a/server/tests/test_budget.py b/server/tests/test_budget.py\n"
    "--- a/server/tests/test_budget.py\n"
    "+++ b/server/tests/test_budget.py\n"
    "@@ -10,0 +11,2 @@\n"
    "+def test_new_budget():\n"
    "+    assert True\n"
    "diff --git a/web/src/budget.test.ts b/web/src/budget.test.ts\n"
    "--- a/web/src/budget.test.ts\n"
    "+++ b/web/src/budget.test.ts\n"
    "@@ -20,0 +21 @@\n"
    '+it.each([1, 2])("renders %s", () => {})\n'
    "diff --git a/ci/tests/test_internal.py b/ci/tests/test_internal.py\n"
    "--- a/ci/tests/test_internal.py\n"
    "+++ b/ci/tests/test_internal.py\n"
    "@@ -0,0 +1 @@\n"
    "+def test_internal(): pass\n"
)


def test_added_test_lines_include_only_product_test_paths() -> None:
    assert added_test_lines(PATCH) == {
        "server/tests/test_budget.py": frozenset({11, 12}),
        "web/src/budget.test.ts": frozenset({21}),
    }


@pytest.mark.parametrize(
    "path",
    [
        "server/tests/unit/test_api.py",
        "server/tests/integration/test_api.PY",
        "web/src/api.test.ts",
        "web/src/Api.test.TSX",
        "web/e2e/api.spec.ts",
        "web/e2e/api.spec.tsx",
    ],
)
def test_product_test_path_scope_accepts_supported_paths(path: str) -> None:
    assert eligible_test_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "server/test_api.py",
        "ci/tests/test_api.py",
        "web/src/api.spec.ts",
        "web/e2e/api.test.ts",
        "other/web/src/api.test.ts",
    ],
)
def test_product_test_path_scope_rejects_unsupported_paths(path: str) -> None:
    assert not eligible_test_path(path)


def test_patch_parser_tracks_context_deletions_markers_and_file_boundaries() -> None:
    patch = (
        "diff --git a/server/tests/test_first.py b/server/tests/test_first.py\n"
        "--- a/server/tests/test_first.py\n"
        "+++ b/server/tests/test_first.py\n"
        "@@ -4,2 +4,3 @@\n"
        " context\n"
        "-removed\n"
        "\\ No newline at end of file\n"
        "+def test_first(): pass\n"
        " context\n"
        "diff --git a/server/tests/incomplete.py b/server/tests/incomplete.py\n"
        "@@ -0,0 +1 @@\n"
        "+def test_ignored(): pass\n"
        "diff --git a/web/e2e/second.spec.ts b/web/e2e/second.spec.ts\n"
        "--- a/web/e2e/second.spec.ts\n"
        "+++ b/web/e2e/second.spec.ts\n"
        "@@ -0,0 +8 @@\n"
        "+test('second', () => {})\n"
    )

    assert added_test_lines(patch) == {
        "server/tests/test_first.py": frozenset({5}),
        "web/e2e/second.spec.ts": frozenset({8}),
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/repo/server/tests/test_api.py", "server/tests/test_api.py"),
        ("/repo/web/src/api.test.ts", "web/src/api.test.ts"),
        ("./relative.test.ts", "relative.test.ts"),
    ],
)
def test_collected_paths_are_repository_relative(value: str, expected: str) -> None:
    assert repository_path(value) == expected


def test_native_collection_selects_each_expanded_case_on_an_added_definition() -> None:
    collected = (
        CollectedTest(
            RunnerStack.PYTEST,
            Lane.FAST,
            "server/tests/test_budget.py",
            11,
            "server/tests/test_budget.py::test_new_budget",
            "test_new_budget",
        ),
        CollectedTest(
            RunnerStack.VITEST,
            Lane.FAST,
            "web/src/budget.test.ts",
            21,
            "budget.test.ts::renders 1",
            "renders 1",
        ),
        CollectedTest(
            RunnerStack.VITEST,
            Lane.FAST,
            "web/src/budget.test.ts",
            21,
            "budget.test.ts::renders 2",
            "renders 2",
        ),
        CollectedTest(
            RunnerStack.VITEST,
            Lane.FAST,
            "web/src/budget.test.ts",
            8,
            "budget.test.ts::existing",
            "existing",
        ),
        CollectedTest(
            RunnerStack.PLAYWRIGHT,
            Lane.SLOW,
            "web/e2e/unrelated.spec.ts",
            3,
            "unrelated-id",
            "unrelated",
        ),
    )

    selected = select_added_tests(collected, added_test_lines(PATCH))

    assert [test.runner_id for test in selected] == [
        "server/tests/test_budget.py::test_new_budget",
        "budget.test.ts::renders 1",
        "budget.test.ts::renders 2",
    ]
    assert len({test.finding_id for test in selected}) == 3


def test_pytest_collection_expands_parameterized_node_ids() -> None:
    source = (
        "import pytest\n\n"
        "@pytest.mark.parametrize('value', [1, 2])\n"
        "def test_value(value: int) -> None:\n"
        "    assert value\n\n"
        "class TestGroup:\n"
        "    async def test_method(self) -> None:\n"
        "        assert True\n"
    )
    output = (
        "server/tests/test_values.py::test_value[1]\n"
        "server/tests/test_values.py::test_value[2]\n"
        "server/tests/test_values.py::TestGroup::test_method\n"
    )

    tests = parse_pytest_collection(output, {"server/tests/test_values.py": source})

    assert [(test.runner_id, test.line) for test in tests] == [
        ("server/tests/test_values.py::test_value[1]", 4),
        ("server/tests/test_values.py::test_value[2]", 4),
        ("server/tests/test_values.py::TestGroup::test_method", 8),
    ]
    assert tests[0].lane is Lane.FAST


def test_pytest_integration_collection_ignores_noise_and_unknown_nodes() -> None:
    source = (
        "def test_first() -> None:\n"
        "    assert True\n\n"
        "def test_second() -> None:\n"
        "    assert True\n"
    )
    output = (
        "server/tests/integration/test_api.py::test_first\n"
        "server/tests/integration/test_api.py::test_missing\n"
        "2 tests collected in 0.01s\n"
        "server/tests/integration/test_api.py::test_second\n"
    )

    tests = parse_pytest_collection(output, {"server/tests/integration/test_api.py": source})

    assert [(test.name, test.line, test.lane) for test in tests] == [
        ("test_first", 1, Lane.MEDIUM),
        ("test_second", 4, Lane.MEDIUM),
    ]


def test_vitest_collection_uses_expanded_names_and_native_locations() -> None:
    payload = json.dumps(
        [
            {
                "name": "budget > renders 1",
                "file": "/repo/web/src/budget.test.tsx",
                "location": {"line": 21, "column": 5},
            },
            {
                "name": "budget > renders 2",
                "file": "/repo/web/src/budget.test.tsx",
                "location": {"line": 21, "column": 5},
            },
        ]
    )

    tests = parse_vitest_collection(payload)

    assert [(test.runner_id, test.lane, test.line) for test in tests] == [
        ("budget > renders 1", Lane.MEDIUM, 21),
        ("budget > renders 2", Lane.MEDIUM, 21),
    ]


def test_vitest_collection_rejects_non_array_and_skips_malformed_entries() -> None:
    with pytest.raises(TypeError, match="Vitest collection must be a JSON array"):
        parse_vitest_collection("{}")

    payload = json.dumps(
        [
            None,
            {"name": 1, "file": "x", "location": {}},
            {
                "name": "valid",
                "file": "/repo/web/src/value.test.ts",
                "location": {"line": 3},
            },
        ]
    )

    assert parse_vitest_collection(payload) == (
        CollectedTest(
            RunnerStack.VITEST,
            Lane.FAST,
            "web/src/value.test.ts",
            3,
            "valid",
            "valid",
        ),
    )


def test_playwright_collection_flattens_specs_into_slow_cases() -> None:
    payload = json.dumps(
        {
            "suites": [
                {
                    "title": "budget.spec.ts",
                    "suites": [
                        {
                            "title": "budget",
                            "specs": [
                                {
                                    "title": "creates a category",
                                    "id": "case-id",
                                    "file": "budget.spec.ts",
                                    "line": 17,
                                    "column": 3,
                                }
                            ],
                        }
                    ],
                    "specs": [],
                }
            ]
        }
    )

    tests = parse_playwright_collection(payload)

    assert tests == (
        CollectedTest(
            RunnerStack.PLAYWRIGHT,
            Lane.SLOW,
            "web/e2e/budget.spec.ts",
            17,
            "case-id",
            "budget > creates a category",
        ),
    )


def test_playwright_collection_rejects_missing_suites() -> None:
    with pytest.raises(TypeError, match="Playwright collection must contain suites"):
        parse_playwright_collection("{}")


def test_playwright_collection_does_not_duplicate_reporter_e2e_prefix() -> None:
    payload = json.dumps(
        {
            "suites": [
                {
                    "title": "budget.spec.ts",
                    "specs": [
                        {
                            "title": "works",
                            "id": "case-id",
                            "file": "e2e/budget.spec.ts",
                            "line": 4,
                        }
                    ],
                }
            ]
        }
    )

    assert parse_playwright_collection(payload)[0].path == "web/e2e/budget.spec.ts"


class FakeRunner:
    def __init__(self, failures: set[int]) -> None:
        self.failures = failures
        self.calls: list[tuple[str, int]] = []

    def run(self, test: CollectedTest, attempt: int) -> AttemptResult:
        self.calls.append((test.runner_id, attempt))
        status = AttemptStatus.FAILED if attempt in self.failures else AttemptStatus.PASSED
        return AttemptResult(attempt, status, 0.1, "boom" if attempt in self.failures else "")


def test_each_added_case_runs_ten_times_without_stopping_after_failure() -> None:
    test = CollectedTest(
        RunnerStack.PYTEST,
        Lane.FAST,
        "server/tests/test_budget.py",
        11,
        "server/tests/test_budget.py::test_new_budget",
        "test_new_budget",
    )
    runner = FakeRunner({4})

    results = repeat_tests((test,), {RunnerStack.PYTEST: runner})

    assert [attempt.status for attempt in results[0].attempts] == [
        AttemptStatus.PASSED,
        AttemptStatus.PASSED,
        AttemptStatus.PASSED,
        AttemptStatus.FAILED,
        AttemptStatus.PASSED,
        AttemptStatus.PASSED,
        AttemptStatus.PASSED,
        AttemptStatus.PASSED,
        AttemptStatus.PASSED,
        AttemptStatus.PASSED,
    ]
    assert results[0].unstable
    assert results[0].test == test
    assert runner.calls == [(test.runner_id, attempt) for attempt in range(1, 11)]


class FakeExecutor:
    def __init__(self, result: ProcessResult) -> None:
        self.result = result
        self.calls: list[tuple[tuple[str, ...], str, float]] = []

    def run(self, command: tuple[str, ...], cwd: str, timeout_seconds: float) -> ProcessResult:
        self.calls.append((command, cwd, timeout_seconds))
        return self.result


def test_runner_adapters_select_one_case_and_disable_retries() -> None:
    executor = FakeExecutor(ProcessResult(0, "ok", 0.2))
    pytest_test = CollectedTest(
        RunnerStack.PYTEST,
        Lane.FAST,
        "server/tests/test_budget.py",
        11,
        "server/tests/test_budget.py::test_new_budget[usd]",
        "test_new_budget[usd]",
    )
    vitest_test = CollectedTest(
        RunnerStack.VITEST,
        Lane.MEDIUM,
        "web/src/Budget.test.tsx",
        21,
        "budget > renders [usd]",
        "budget > renders [usd]",
    )
    playwright_test = CollectedTest(
        RunnerStack.PLAYWRIGHT,
        Lane.SLOW,
        "web/e2e/budget.spec.ts",
        17,
        "playwright-id",
        "budget > creates [usd]",
    )

    assert PytestRunner(executor).run(pytest_test, 1).status is AttemptStatus.PASSED
    assert VitestRunner(executor).run(vitest_test, 2).status is AttemptStatus.PASSED
    assert PlaywrightRunner(executor).run(playwright_test, 3).status is AttemptStatus.PASSED

    pytest_command, pytest_cwd, pytest_timeout = executor.calls[0]
    assert pytest_command[-1] == pytest_test.runner_id
    assert pytest_cwd == "."
    assert pytest_timeout == 60
    vitest_command, vitest_cwd, vitest_timeout = executor.calls[1]
    assert "--retry=0" in vitest_command
    assert r"^budget\ >\ renders\ \[usd\]$" in vitest_command
    assert vitest_cwd == "web"
    assert vitest_timeout == 120
    playwright_command, playwright_cwd, playwright_timeout = executor.calls[2]
    assert "--retries=0" in playwright_command
    assert "e2e/budget.spec.ts:17" in playwright_command
    assert r"creates\ \[usd\]$" in playwright_command
    assert playwright_cwd == "web"
    assert playwright_timeout == 180


def test_adapter_classifies_timeout_runner_error_and_test_failure() -> None:
    test = CollectedTest(
        RunnerStack.PYTEST,
        Lane.FAST,
        "server/tests/test_budget.py",
        11,
        "server/tests/test_budget.py::test_new_budget",
        "test_new_budget",
    )

    assert (
        PytestRunner(FakeExecutor(ProcessResult(None, "late", 60, timed_out=True)))
        .run(test, 1)
        .status
        is AttemptStatus.TIMED_OUT
    )
    assert (
        PytestRunner(FakeExecutor(ProcessResult(1, "assertion", 0.2))).run(test, 1).status
        is AttemptStatus.FAILED
    )
    assert (
        PytestRunner(FakeExecutor(ProcessResult(2, "usage error", 0.2))).run(test, 1).status
        is AttemptStatus.RUNNER_ERROR
    )
