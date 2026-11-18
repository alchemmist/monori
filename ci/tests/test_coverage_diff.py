import json
import sys
from pathlib import Path

import pytest

from monori.ci.lib.coverage_diff import (
    COVERAGE_REPORT_ADAPTER,
    CoverageReport,
    Finding,
    ReportInputs,
    StackReport,
    build_report,
    coverage_totals,
    diff_stats,
    function_name,
    group_findings,
    load_baseline,
    markdown_cell,
    normalize_lcov,
    python_function,
    render_summary,
    typescript_function,
    write_baseline,
    write_report,
)
from monori.ci.lib.coverage_diff import main as coverage_main
from monori.common import JsonValue

READ_ERROR = "unreadable"


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
    tmp_path: Path, contents: str, message: str
) -> None:
    baseline = tmp_path / "baseline.json"
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


def test_failure_summary_explains_both_signals_and_names_function() -> None:
    body = render_summary(report(passed=False), workflow_passed=True)

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


def test_failure_summary_reports_each_independent_failure() -> None:
    coverage_failure = report()
    coverage_failure.coverage_ok = False
    assert "existing absolute coverage floor failed" in render_summary(
        coverage_failure, workflow_passed=True
    )

    incomplete = report()
    incomplete.stacks[0].error = "missing diff"
    assert "coverage evidence was incomplete" in render_summary(incomplete, workflow_passed=True)

    workflow_failure = report()
    assert "coverage job" in render_summary(workflow_failure, workflow_passed=False)


def test_failure_summary_escapes_untrusted_artifact_text() -> None:
    unsafe = report(passed=False)
    unsafe.stacks[0].findings = [
        Finding(path="bad|path\n## heading.py", function="`breakout`", start=4, end=4)
    ]

    body = render_summary(unsafe, workflow_passed=True)

    assert "bad\\|path ## heading.py" in body
    assert "&#x27;breakout&#x27;" in body
    assert markdown_cell("a|b\r\n`c`") == "a\\|b  &#x27;c&#x27;"


def test_clean_summary_collapses_to_one_line() -> None:
    assert render_summary(report(), workflow_passed=True) == (
        "✅ New code covered, total coverage did not drop — all good.\n"
    )


def test_clean_summary_discloses_an_inactive_total_regression_gate() -> None:
    clean = report()
    clean.stacks[0].baseline = None

    summary = render_summary(clean, workflow_passed=True)

    assert summary == (
        "✅ New code covered, total coverage did not drop — all good.\n\n"
        "⚠️ Total-coverage regression gate inactive: "
        "the base coverage baseline was unavailable.\n"
    )


def test_cli_baseline_and_normalize_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frontend = tmp_path / "frontend.json"
    backend = tmp_path / "backend.json"
    baseline = tmp_path / "baseline.json"
    frontend.write_text(json.dumps({"total": {"lines": {"pct": 91}}}))
    backend.write_text(json.dumps({"totals": {"percent_covered": 82}}))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "coverage-diff",
            "baseline",
            "--frontend",
            str(frontend),
            "--backend",
            str(backend),
            "--output",
            str(baseline),
        ],
    )
    assert coverage_main() == 0
    assert load_baseline(baseline) == {"backend": 82.0, "frontend": 91.0}

    source = tmp_path / "lcov.info"
    normalized = tmp_path / "normalized.info"
    source.write_text("SF:src/example.ts\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "coverage-diff",
            "normalize-lcov",
            "--input",
            str(source),
            "--output",
            str(normalized),
        ],
    )
    assert coverage_main() == 0
    assert normalized.read_text() == "SF:web/src/example.ts\n"


def test_cli_report_returns_report_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "report.json"
    monkeypatch.setattr("monori.ci.lib.coverage_diff.build_report", lambda _inputs: report())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "coverage-diff",
            "report",
            "--frontend",
            "frontend.json",
            "--backend",
            "backend.json",
            "--frontend-diff",
            "frontend-diff.json",
            "--backend-diff",
            "backend-diff.json",
            "--baseline",
            "baseline.json",
            "--base",
            "origin/main",
            "--coverage-exit",
            "0",
            "--output",
            str(output),
        ],
    )
    assert coverage_main() == 0
    assert COVERAGE_REPORT_ADAPTER.validate_json(output.read_bytes()).passed


def test_diff_stats_fails_closed_for_missing_and_invalid_reports(tmp_path: Path) -> None:
    assert diff_stats(tmp_path / "missing.json") == (
        0,
        0,
        0,
        [],
        "Diff coverage report was not produced",
    )
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{")
    assert diff_stats(invalid)[4] is not None


def test_build_and_write_report_use_touched_stack_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frontend = tmp_path / "frontend.json"
    backend = tmp_path / "backend.json"
    baseline = tmp_path / "baseline.json"
    frontend_diff = tmp_path / "frontend-diff.json"
    backend_diff = tmp_path / "backend-diff.json"
    output = tmp_path / "nested/report.json"
    frontend.write_text(json.dumps({"total": {"lines": {"pct": 91}}}))
    backend.write_text(json.dumps({"totals": {"percent_covered": 82}}))
    baseline.write_text(
        json.dumps({"schema_version": 1, "stacks": {"backend": 82, "frontend": 91}})
    )
    monkeypatch.setattr(
        "monori.ci.lib.coverage_diff.changed_paths", lambda _base: {"server/app/example.py"}
    )
    monkeypatch.setattr(
        "monori.ci.lib.coverage_diff.diff_stats", lambda _path: (100, 1, 1, [], None)
    )
    built = build_report(
        ReportInputs(
            frontend,
            backend,
            frontend_diff,
            backend_diff,
            baseline,
            "origin/main",
            0,
        )
    )
    assert [stack.touched for stack in built.stacks] == [True, False]
    write_report(built, output)
    assert COVERAGE_REPORT_ADAPTER.validate_json(output.read_bytes()) == built
