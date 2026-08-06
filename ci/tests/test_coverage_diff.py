import json
from pathlib import Path
from typing import cast, override

import pytest

from monori.ci.lib.coverage_diff import (
    COVERAGE_REPORT_ADAPTER,
    CoverageReport,
    Finding,
    PublishInputs,
    StackReport,
    coverage_job_passed,
    coverage_totals,
    group_findings,
    load_artifact,
    load_baseline,
    normalize_lcov,
    publish_report,
    render_report,
    write_baseline,
)
from monori.common import JsonValue

HEAD_SHA = "a" * 40


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
    output = tmp_path / "baseline.json"
    frontend.write_text(json.dumps({"total": {"lines": {"pct": 91.25}}}))
    backend.write_text(json.dumps({"totals": {"percent_covered": 82.5}}))

    assert coverage_totals(frontend, backend) == {"frontend": 91.25, "backend": 82.5}
    write_baseline(frontend, backend, output)

    assert json.loads(output.read_text()) == {
        "schema_version": 1,
        "stacks": {"backend": 82.5, "frontend": 91.25},
    }


@pytest.mark.parametrize(
    "contents",
    [
        None,
        "{",
        json.dumps({"schema_version": 2, "stacks": {"backend": 80, "frontend": 90}}),
        json.dumps({"schema_version": 1, "stacks": {"backend": 80}}),
        json.dumps({"schema_version": 1, "stacks": {"backend": 80, "frontend": "invalid"}}),
    ],
)
def test_baseline_validation_fails_closed(tmp_path: Path, contents: str | None) -> None:
    baseline = tmp_path / "baseline.json"
    if contents is not None:
        baseline.write_text(contents)

    with pytest.raises(ValueError, match="Coverage baseline"):
        load_baseline(baseline)


def test_normalizes_frontend_lcov_paths(tmp_path: Path) -> None:
    source = tmp_path / "lcov.info"
    output = tmp_path / "normalized.info"
    source.write_text("TN:\nSF:src/example.ts\nDA:1,1\nend_of_record\n")

    normalize_lcov(source, output)

    assert "SF:web/src/example.ts" in output.read_text()


def test_clean_removes_backend_coverage_xml() -> None:
    assert "server/coverage.xml" in Path("Makefile").read_text()


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


def test_failure_comment_explains_both_signals_and_names_function() -> None:
    body = render_report(report(passed=False), workflow_passed=True)

    assert "total coverage dropped" in body
    assert "new or changed executable lines are not covered" in body
    assert "`server/app/example.py` | `calculate` | 4" in body


def test_failure_comment_escapes_untrusted_artifact_text() -> None:
    unsafe = report(passed=False)
    unsafe.stacks[0].findings = [
        Finding(path="bad|path\n## heading.py", function="`breakout`", start=4, end=4)
    ]

    body = render_report(unsafe, workflow_passed=True)

    assert "bad\\|path ## heading.py" in body
    assert "&#x27;breakout&#x27;" in body


def test_clean_comment_collapses_to_one_line() -> None:
    assert render_report(report(), workflow_passed=True) == (
        "✅ New code covered, total coverage did not drop — all good.\n"
    )


def test_artifact_validation_rejects_wrong_workflow_metadata(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_bytes(COVERAGE_REPORT_ADAPTER.dump_json(report()))

    with pytest.raises(ValueError, match="metadata does not match"):
        load_artifact(artifact, "b" * 40, 7)


def test_artifact_validation_requires_both_stacks(tmp_path: Path) -> None:
    data = json.loads(COVERAGE_REPORT_ADAPTER.dump_json(report()))
    data["stacks"][1]["name"] = "backend"
    artifact = tmp_path / "report.json"
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="backend and frontend"):
        load_artifact(artifact, HEAD_SHA, 7)


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
        PublishInputs(artifact, 11, 7, HEAD_SHA, "https://example.test/run/11"),
    )

    comment = next(request for request in github.requests if request[1] == "/issues/7/comments")
    status = next(request for request in github.requests if request[1] == f"/statuses/{HEAD_SHA}")
    assert "<!-- monori-report: coverage -->" in cast("dict[str, str]", comment[2])["body"]
    assert cast("dict[str, str]", status[2])["state"] == "success"


def test_privileged_publisher_fails_closed_when_artifact_is_missing(tmp_path: Path) -> None:
    github = FakeGitHub()

    assert not publish_report(
        github,
        PublishInputs(tmp_path / "missing.json", 11, 7, HEAD_SHA, "https://example.test/run/11"),
    )

    comment = next(request for request in github.requests if request[1] == "/issues/7/comments")
    status = next(request for request in github.requests if request[1] == f"/statuses/{HEAD_SHA}")
    assert "could not be validated" in cast("dict[str, str]", comment[2])["body"]
    assert cast("dict[str, str]", status[2])["state"] == "failure"


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
        PublishInputs(artifact, 11, 7, HEAD_SHA, "https://example.test/run/11"),
    )

    comment = next(request for request in github.requests if request[1] == "/issues/7/comments")
    assert "does not match" in cast("dict[str, str]", comment[2])["body"]
