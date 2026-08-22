import json
from pathlib import Path
from typing import cast, override

import pytest
from pydantic import ValidationError

from monori.ci.lib.coverage_diff import (
    COVERAGE_REPORT_ADAPTER,
    CoverageReport,
    Finding,
    PublishInputs,
    StackReport,
    coverage_job_passed,
    coverage_totals,
    function_name,
    group_findings,
    load_artifact,
    load_baseline,
    markdown_cell,
    normalize_lcov,
    publish_report,
    python_function,
    render_report,
    resolve_pull_request,
    typescript_function,
    write_baseline,
)
from monori.common import JsonValue

HEAD_SHA = "a" * 40
JOBS_UNAVAILABLE = "jobs unavailable"


def report(*, passed: bool = True) -> CoverageReport:
    backend = StackReport(
        name="backend",
        touched=True,
        total=82.5 if passed else 79.5,
        baseline=82.0,
        patch=100 if passed else 50,
        covered_lines=2 if passed else 1,
        changed_lines=2,
        findings=[]
        if passed
        else [Finding(path="server/app/example.py", function="calculate", start=4, end=4)],
    )
    frontend = StackReport(
        name="frontend",
        touched=False,
        total=91,
        patch=100,
        covered_lines=0,
        changed_lines=0,
        findings=[],
    )
    return CoverageReport(
        schema_version=1,
        pr_number=7,
        head_sha=HEAD_SHA,
        coverage_ok=True,
        stacks=[backend, frontend],
    )


def test_reads_native_totals_and_writes_baseline(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend.json"
    backend = tmp_path / "backend.json"
    output = tmp_path / "nested/deep/baseline.json"
    frontend.write_text(json.dumps({"total": {"lines": {"pct": 91.25}}}))
    backend.write_text(json.dumps({"totals": {"percent_covered": 82.5}}))

    assert coverage_totals(frontend, backend) == {"frontend": 91.25, "backend": 82.5}
    write_baseline(frontend, backend, output)

    assert output.read_text() == (
        '{\n  "schema_version": 1,\n  "stacks": {\n'
        '    "backend": 82.5,\n    "frontend": 91.25\n  }\n}\n'
    )
    write_baseline(frontend, backend, output)


@pytest.mark.parametrize(
    ("frontend_data", "backend_data", "message"),
    [
        ([], {"totals": {"percent_covered": 82.5}}, "Expected JSON object for frontend coverage"),
        ({}, {"totals": {"percent_covered": 82.5}}, "Expected JSON object for frontend total"),
        (
            {"total": {}},
            {"totals": {"percent_covered": 82.5}},
            "Expected JSON object for frontend lines",
        ),
        (
            {"total": {"lines": {}}},
            {"totals": {"percent_covered": 82.5}},
            "Expected JSON number for frontend line percent",
        ),
        (
            {"total": {"lines": {"pct": "bad"}}},
            {"totals": {"percent_covered": 82.5}},
            "Expected JSON number for frontend line percent",
        ),
        (
            {"total": {"lines": {"pct": 91.25}}},
            [],
            "Expected JSON object for backend coverage",
        ),
        (
            {"total": {"lines": {"pct": 91.25}}},
            {},
            "Expected JSON object for backend totals",
        ),
        (
            {"total": {"lines": {"pct": 91.25}}},
            {"totals": {}},
            "Expected JSON number for backend line percent",
        ),
        (
            {"total": {"lines": {"pct": 91.25}}},
            {"totals": {"percent_covered": "bad"}},
            "Expected JSON number for backend line percent",
        ),
    ],
)
def test_native_totals_reject_incomplete_inputs(
    tmp_path: Path, frontend_data: JsonValue, backend_data: JsonValue, message: str
) -> None:
    frontend = tmp_path / "frontend.json"
    backend = tmp_path / "backend.json"
    frontend.write_text(json.dumps(frontend_data))
    backend.write_text(json.dumps(backend_data))

    with pytest.raises(TypeError) as error:
        coverage_totals(frontend, backend)

    assert str(error.value) == message


@pytest.mark.parametrize(
    "contents",
    [
        "{",
        json.dumps({"schema_version": 2, "stacks": {"backend": 80, "frontend": 90}}),
        json.dumps({"schema_version": 1, "stacks": {"backend": 80}}),
        json.dumps({"schema_version": 1, "stacks": {"backend": 80, "frontend": "invalid"}}),
        json.dumps({"schema_version": 1, "stacks": {"backend": -1, "frontend": 90}}),
        json.dumps({"schema_version": 1, "stacks": {"backend": 101, "frontend": 90}}),
        json.dumps({"schema_version": 1, "stacks": {"backend": 80, "frontend": float("inf")}}),
        json.dumps({"schema_version": 1, "stacks": {"backend": 80, "frontend": float("nan")}}),
    ],
)
def test_baseline_validation_fails_closed(tmp_path: Path, contents: str | None) -> None:
    baseline = tmp_path / "baseline.json"
    if contents is not None:
        baseline.write_text(contents)

    with pytest.raises(ValueError, match="Coverage baseline"):
        load_baseline(baseline)


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{", "Coverage baseline is invalid"),
        (
            json.dumps({"schema_version": 2, "stacks": {"backend": 80, "frontend": 90}}),
            "Coverage baseline schema is unsupported",
        ),
        (
            json.dumps({"schema_version": 1, "stacks": {"backend": 80}}),
            "Coverage baseline must contain backend and frontend stacks",
        ),
        (
            json.dumps({"schema_version": 1, "stacks": {"backend": -1, "frontend": 90}}),
            "Coverage baseline values must be finite percentages",
        ),
    ],
)
def test_baseline_validation_reports_the_exact_failure(
    tmp_path: Path, contents: str | None, message: str
) -> None:
    baseline = tmp_path / "baseline.json"
    if contents is not None:
        baseline.write_text(contents)

    with pytest.raises(ValueError, match=message) as error:
        load_baseline(baseline)

    assert str(error.value) == message


def test_loads_valid_baseline_as_floats(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"schema_version": 1, "stacks": {"backend": 80, "frontend": 90.5}})
    )

    assert load_baseline(baseline) == {"backend": 80.0, "frontend": 90.5}


def test_missing_baseline_keeps_total_delta_neutral(tmp_path: Path) -> None:
    assert load_baseline(tmp_path / "missing.json") is None


def test_normalizes_frontend_lcov_paths(tmp_path: Path) -> None:
    source = tmp_path / "lcov.info"
    output = tmp_path / "normalized.info"
    source.write_text("TN:\nSF:src/example.ts\nDA:1,1\nend_of_record\n")

    normalize_lcov(source, output)

    assert output.read_text() == "TN:\nSF:web/src/example.ts\nDA:1,1\nend_of_record\n"


def test_normalize_lcov_preserves_non_source_paths(tmp_path: Path) -> None:
    source = tmp_path / "lcov.info"
    output = tmp_path / "normalized.info"
    source.write_text("SF:web/src/example.ts\nSF:/absolute/example.ts\n")

    normalize_lcov(source, output)

    assert output.read_text() == "SF:web/src/example.ts\nSF:/absolute/example.ts\n"


def test_clean_removes_backend_coverage_xml() -> None:
    assert "server/coverage.xml" in Path("Makefile").read_text()


def test_coverage_diff_discards_stale_report_artifacts() -> None:
    makefile = Path("Makefile").read_text()

    assert "rm -rf coverage-report && mkdir -p coverage-report || exit 1" in makefile


def test_groups_uncovered_python_lines_by_function(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_text(
        "def calculate():\n    first = 1\n    second = 2\n    return first + second\n"
    )
    raw: dict[str, JsonValue] = {
        "src_stats": {
            str(source): {
                "violation_lines": [2, 3, 4],
            }
        }
    }

    assert group_findings(raw) == [Finding(path=str(source), function="calculate", start=2, end=4)]


def test_groups_sorted_disjoint_findings_and_ignores_non_integer_lines(tmp_path: Path) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.ts"
    first.write_text("value = 1\ndef later():\n    return 2\n")
    second.write_text("const run = () => {\n  return 1\n}\n")
    raw: dict[str, JsonValue] = {
        "src_stats": {
            str(second): {"violation_lines": [2]},
            str(first): {"violation_lines": [3, "bad", 1]},
        }
    }

    assert group_findings(raw) == [
        Finding(path=str(first), function="(module)", start=1, end=1),
        Finding(path=str(first), function="later", start=3, end=3),
        Finding(path=str(second), function="run", start=2, end=2),
    ]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"src_stats": []}, "Expected JSON object for diff-cover src_stats"),
        (
            {"src_stats": {"file.py": []}},
            "Expected JSON object for diff-cover stats for file.py",
        ),
        (
            {"src_stats": {"file.py": {"violation_lines": {}}}},
            "Expected JSON array for file.py",
        ),
    ],
)
def test_group_findings_rejects_invalid_diff_cover_shapes(
    raw: dict[str, JsonValue], message: str
) -> None:
    with pytest.raises(TypeError) as error:
        group_findings(raw)

    assert str(error.value) == message


def test_function_resolution_handles_nested_and_invalid_sources(tmp_path: Path) -> None:
    nested = tmp_path / "nested.py"
    nested.write_text("def outer():\n    def inner():\n        return 1\n    return inner()\n")
    invalid = tmp_path / "invalid.py"
    invalid.write_text("def broken(\n")
    missing = tmp_path / "missing.py"

    assert python_function(nested, 3) == "inner"
    assert python_function(nested, 4) == "outer"
    assert python_function(nested, 1) == "outer"
    assert python_function(invalid, 1) == "(module)"
    assert python_function(missing, 1) == "(module)"
    assert function_name(str(nested), 3) == "inner"


@pytest.mark.parametrize(
    ("source", "line", "expected"),
    [
        ("function named() {\n  return 1\n}\n", 2, "named"),
        ("const arrow = () => {\n  return 1\n}\n", 2, "arrow"),
        ("let classic = function () {\n  return 1\n}\n", 2, "classic"),
        ("async method() {\n  return 1\n}\n", 2, "method"),
        ("if (ready) {\n  return 1\n}\n", 2, "(module)"),
    ],
)
def test_typescript_function_patterns(
    tmp_path: Path, source: str, line: int, expected: str
) -> None:
    path = tmp_path / "example.ts"
    path.write_text(source)

    assert typescript_function(path, line) == expected
    assert function_name(str(path), line) == expected


def test_failure_comment_explains_both_signals_and_names_function() -> None:
    body = render_report(report(passed=False), workflow_passed=True)

    assert (
        body
        == """## ❌ Coverage

This check failed because:
- total coverage dropped relative to `main`
- new or changed executable lines are not covered

| Stack | Total | Delta | Patch |
| --- | ---: | ---: | ---: |
| backend | 79.50% | -2.50% | 1/2 (50.00%) |

Add tests that execute these changed lines:

| File | Function | Uncovered lines |
| --- | --- | ---: |
| `server/app/example.py` | `calculate` | 4 |
"""
    )


def test_failure_comment_reports_each_independent_failure() -> None:
    coverage_failure = report()
    coverage_failure.coverage_ok = False
    assert "existing absolute coverage floor failed" in render_report(
        coverage_failure, workflow_passed=True
    )

    incomplete = report()
    incomplete.stacks[0].error = "missing diff"
    assert "coverage evidence was incomplete" in render_report(incomplete, workflow_passed=True)

    workflow_failure = report()
    assert "coverage job" in render_report(workflow_failure, workflow_passed=False)


def test_failure_comment_escapes_untrusted_artifact_text() -> None:
    unsafe = report(passed=False)
    unsafe.stacks[0].findings = [
        Finding(path="bad|path\n## heading.py", function="`breakout`", start=4, end=4)
    ]

    body = render_report(unsafe, workflow_passed=True)

    assert "bad\\|path ## heading.py" in body
    assert "&#x27;breakout&#x27;" in body
    assert markdown_cell("a|b\r\n`c`") == "a\\|b  &#x27;c&#x27;"


def test_clean_comment_collapses_to_one_line() -> None:
    assert render_report(report(), workflow_passed=True) == (
        "✅ New code covered, total coverage did not drop — all good.\n"
    )


def test_artifact_validation_rejects_wrong_workflow_metadata(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_bytes(COVERAGE_REPORT_ADAPTER.dump_json(report()))

    with pytest.raises(ValueError, match="metadata does not match") as error:
        load_artifact(artifact, "b" * 40, 7)

    assert str(error.value) == "Coverage artifact metadata does not match the workflow run"


def test_artifact_validation_requires_both_stacks(tmp_path: Path) -> None:
    data = json.loads(COVERAGE_REPORT_ADAPTER.dump_json(report()))
    data["stacks"][1]["name"] = "backend"
    artifact = tmp_path / "report.json"
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="backend and frontend"):
        load_artifact(artifact, HEAD_SHA, 7)


def test_artifact_validation_accepts_matching_metadata(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_bytes(COVERAGE_REPORT_ADAPTER.dump_json(report()))

    assert load_artifact(artifact, HEAD_SHA, 7) == report()


def test_artifact_validation_rejects_oversized_input(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_bytes(b"x" * 1_000_001)

    with pytest.raises(ValueError, match="size limit") as error:
        load_artifact(artifact, HEAD_SHA, 7)

    assert str(error.value) == "Coverage artifact exceeds the size limit"


def test_artifact_size_limit_is_inclusive_of_the_maximum(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_bytes(b"x" * 1_000_000)

    with pytest.raises(ValidationError) as error:
        load_artifact(artifact, HEAD_SHA, 7)

    assert "size limit" not in str(error.value)


class FakeGitHub:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, JsonValue]] = []

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        self.requests.append((method, path, payload))
        if path == f"/commits/{HEAD_SHA}/pulls":
            return [{"number": 7, "state": "open", "head": {"sha": HEAD_SHA}}]
        if path == "/actions/runs/11/jobs?page=1&per_page=100":
            return {"jobs": [{"name": "Coverage", "conclusion": "success"}]}
        if path.startswith("/issues/7/comments?"):
            return []
        return {}


def test_privileged_publisher_uses_job_conclusion_and_upserts_one_comment(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_bytes(COVERAGE_REPORT_ADAPTER.dump_json(report()))
    github = FakeGitHub()

    assert publish_report(
        github,
        PublishInputs(artifact, 11, HEAD_SHA, "https://example.test/run/11"),
    )

    comment = next(request for request in github.requests if request[1] == "/issues/7/comments")
    status = next(request for request in github.requests if request[1] == f"/statuses/{HEAD_SHA}")
    assert "<!-- monori-report: coverage -->" in cast("dict[str, str]", comment[2])["body"]
    assert cast("dict[str, str]", status[2])["state"] == "success"
    assert github.requests == [
        ("GET", f"/commits/{HEAD_SHA}/pulls", None),
        ("GET", "/actions/runs/11/jobs?page=1&per_page=100", None),
        ("GET", "/issues/7/comments?per_page=100&page=1", None),
        (
            "POST",
            "/issues/7/comments",
            {
                "body": "<!-- monori-report: coverage -->\n\n"
                "✅ New code covered, total coverage did not drop — all good.\n"
            },
        ),
        (
            "POST",
            f"/statuses/{HEAD_SHA}",
            {
                "state": "success",
                "target_url": "https://example.test/run/11",
                "description": "Coverage passed",
                "context": "coverage / patch",
            },
        ),
    ]


def test_privileged_publisher_fails_closed_when_artifact_is_missing(tmp_path: Path) -> None:
    github = FakeGitHub()

    assert not publish_report(
        github,
        PublishInputs(tmp_path / "missing.json", 11, HEAD_SHA, "https://example.test/run/11"),
    )

    comment = next(request for request in github.requests if request[1] == "/issues/7/comments")
    status = next(request for request in github.requests if request[1] == f"/statuses/{HEAD_SHA}")
    assert cast("dict[str, str]", comment[2])["body"] == (
        "<!-- monori-report: coverage -->\n\n## ❌ Coverage\n\n"
        "Coverage evidence could not be validated: [Errno 2] No such file or directory: "
        f"&#x27;{tmp_path}/missing.json&#x27;.\n"
    )
    assert status == (
        "POST",
        f"/statuses/{HEAD_SHA}",
        {
            "state": "failure",
            "target_url": "https://example.test/run/11",
            "description": "Coverage failed; see PR comment",
            "context": "coverage / patch",
        },
    )


class PageTwoGitHub(FakeGitHub):
    @override
    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        self.requests.append((method, path, payload))
        if path == "/actions/runs/11/jobs?page=1&per_page=100":
            return {"jobs": [{"name": f"Job {index}"} for index in range(100)]}
        if path == "/actions/runs/11/jobs?page=2&per_page=100":
            return {"jobs": [{"name": "Coverage", "conclusion": "success"}]}
        return {}


def test_coverage_job_lookup_paginates() -> None:
    github = PageTwoGitHub()

    assert coverage_job_passed(github, 11)
    assert any("page=2" in path for _, path, _ in github.requests)


class MissingCoverageJobGitHub(FakeGitHub):
    @override
    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        self.requests.append((method, path, payload))
        if path.endswith("page=1&per_page=100"):
            return {"jobs": [{"name": "Other", "conclusion": "success"}]}
        return {"jobs": []}


def test_coverage_job_lookup_fails_closed_for_missing_or_failed_job() -> None:
    assert not coverage_job_passed(MissingCoverageJobGitHub(), 11)

    class FailedCoverageJobGitHub(FakeGitHub):
        @override
        def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
            if path == "/actions/runs/11/jobs?page=1&per_page=100":
                return {"jobs": [{"name": "Coverage", "conclusion": "failure"}]}
            return super().request(method, path, payload)

    assert not coverage_job_passed(FailedCoverageJobGitHub(), 11)

    class RepeatingJobsGitHub(FakeGitHub):
        @override
        def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
            self.requests.append((method, path, payload))
            return {"jobs": [{"name": "Other", "conclusion": "success"}]}

    github = RepeatingJobsGitHub()

    assert not coverage_job_passed(github, 11)
    assert len(github.requests) == 10


@pytest.mark.parametrize(
    "pulls",
    [
        [],
        [{"number": 7, "state": "closed", "head": {"sha": HEAD_SHA}}],
        [{"number": True, "state": "open", "head": {"sha": HEAD_SHA}}],
        [
            {"number": 7, "state": "open", "head": {"sha": HEAD_SHA}},
            {"number": 8, "state": "open", "head": {"sha": HEAD_SHA}},
        ],
    ],
)
def test_pull_resolution_requires_one_authoritative_match(pulls: JsonValue) -> None:
    class PullsGitHub(FakeGitHub):
        @override
        def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
            return pulls

    with pytest.raises(RuntimeError, match="Expected one open pull request"):
        resolve_pull_request(PullsGitHub(), HEAD_SHA)


def test_pull_resolution_returns_matching_number() -> None:
    github = FakeGitHub()

    assert resolve_pull_request(github, HEAD_SHA) == 7
    assert github.requests == [("GET", f"/commits/{HEAD_SHA}/pulls", None)]


class MismatchedPullGitHub(FakeGitHub):
    @override
    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        if path == f"/commits/{HEAD_SHA}/pulls":
            self.requests.append((method, path, payload))
            return [{"number": 7, "state": "open", "head": {"sha": "b" * 40}}]
        return super().request(method, path, payload)


def test_privileged_publisher_rejects_a_mismatched_pull_head(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_bytes(COVERAGE_REPORT_ADAPTER.dump_json(report()))
    github = MismatchedPullGitHub()

    assert not publish_report(
        github,
        PublishInputs(artifact, 11, HEAD_SHA, "https://example.test/run/11"),
    )

    assert not any(request[1] == "/issues/7/comments" for request in github.requests)
    status = next(request for request in github.requests if request[1] == f"/statuses/{HEAD_SHA}")
    assert cast("dict[str, str]", status[2])["state"] == "failure"


class BrokenJobsGitHub(FakeGitHub):
    @override
    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        if path.startswith("/actions/runs/11/jobs?"):
            raise RuntimeError(JOBS_UNAVAILABLE)
        return super().request(method, path, payload)


def test_privileged_publisher_fails_closed_when_jobs_are_unreadable(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_bytes(COVERAGE_REPORT_ADAPTER.dump_json(report()))
    github = BrokenJobsGitHub()

    assert not publish_report(
        github,
        PublishInputs(artifact, 11, HEAD_SHA, "https://example.test/run/11"),
    )

    comment = next(request for request in github.requests if request[1] == "/issues/7/comments")
    status = next(request for request in github.requests if request[1] == f"/statuses/{HEAD_SHA}")
    assert "jobs unavailable" in cast("dict[str, str]", comment[2])["body"]
    assert cast("dict[str, str]", status[2])["state"] == "failure"
