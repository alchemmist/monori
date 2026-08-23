"""Exercise source Quality Graph gates through the GitHub HTTP client."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, ClassVar, cast, override

import httpx
import pytest

from monori.ci.lib.annotations import SourceAnnotation
from monori.ci.lib.comments import comment_body, upsert_comment
from monori.ci.lib.flaky_tests import (
    AttemptResult,
    AttemptStatus,
    CollectedTest,
    Lane,
    RepetitionResult,
    RunnerStack,
)
from monori.ci.lib.github import GitHub, GitHubAPIError, rerun_latest_pull_request_workflow
from monori.ci.quality_graph.base import ApprovalLifecycle, PullRequestSourceCheck, QualityRuntime
from monori.ci.quality_graph.checks import flaky_tests as flaky_tests_module
from monori.ci.quality_graph.checks.bundle_size import BundleFinding, BundleSizeCheck
from monori.ci.quality_graph.checks.bundle_size import main as bundle_size_main
from monori.ci.quality_graph.checks.flaky_tests import run_check as flaky_tests_run_check
from monori.ci.quality_graph.checks.frontend_performance import (
    main as frontend_performance_main,
)
from monori.ci.quality_graph.checks.object_annotations import main as object_annotations_main
from monori.ci.quality_graph.checks.suppressions import APPROVALS as SUPPRESSION_APPROVALS
from monori.ci.quality_graph.checks.suppressions import main as suppressions_main
from monori.ci.quality_graph.commands import (
    CommandRequest,
    command_request,
    encode_command,
    parse_command,
    process_command,
)
from monori.ci.quality_graph.dashboard import (
    DEFAULT_WATCH_INTERVAL,
    DashboardControlGroup,
    DashboardJob,
    DashboardLifecycle,
    DashboardModel,
    mark_jobs_pending,
    render_dashboard,
    update_dashboard_notice,
)
from monori.ci.quality_graph.job_results import (
    JobControl,
    JobResult,
    JobResultPublisher,
    JobStatus,
    read_job_result,
    write_job_result,
)
from monori.ci.quality_graph.models import CheckContext, CheckResult, Verdict
from monori.ci.quality_graph.registry import workflow_jobs
from monori.ci.quality_graph.reporting import RenderedCheckReport
from monori.common import JsonValue, array_value, object_value, string_value

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from monori.ci.lib.github import RepositoryGitHubAPI

from monori.ci.tests.integration.quality_graph_http_support import (
    BUNDLE_REPORT_COMMENT_ID,
    COMMAND_COMMENT_ID,
    FAILURE_LABEL,
    PULL_REQUEST_NUMBER,
    REPOSITORY,
    SERVICE_UNAVAILABLE,
    ScenarioCheck,
    ScenarioFinding,
    arguments,
    checkbox_body,
    checkbox_event,
    environment,
    fake_state,
    pull_request_event,
    reset_fake_github,
    result_control_body,
    state_objects,
)

pytestmark = pytest.mark.integration


def test_flaky_gate_persists_sticky_evidence_and_publishes_annotations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Keep observed instability blocking across a green rerun on the same head.
    """
    head_sha = "a" * 40
    reset_fake_github(
        {
            "pulls": [
                {
                    "number": PULL_REQUEST_NUMBER,
                    "body": "Pull request body",
                    "html_url": f"https://github.com/{REPOSITORY}/pull/{PULL_REQUEST_NUMBER}",
                    "head": {"sha": head_sha},
                    "base": {"sha": "base-sha"},
                }
            ],
            "comments": [
                {
                    "id": BUNDLE_REPORT_COMMENT_ID,
                    "issue_number": PULL_REQUEST_NUMBER,
                    "body": comment_body("quality-graph", "Initial dashboard"),
                    "user": {"login": "github-actions[bot]"},
                    "reactions": [],
                }
            ],
        }
    )
    test = CollectedTest(
        RunnerStack.PYTEST,
        Lane.FAST,
        "server/tests/test_budget.py",
        11,
        "server/tests/test_budget.py::test_new_budget",
        "test_new_budget",
    )
    failed = RepetitionResult(
        test,
        tuple(
            AttemptResult(
                number,
                AttemptStatus.FAILED if number == 4 else AttemptStatus.PASSED,
                0.1,
                "boom",
            )
            for number in range(1, 11)
        ),
    )
    passed = RepetitionResult(
        test,
        tuple(AttemptResult(number, AttemptStatus.PASSED, 0.1) for number in range(1, 11)),
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text("[]\n")
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "number": PULL_REQUEST_NUMBER,
                    "head": {"sha": head_sha},
                }
            }
        )
    )
    result_path = tmp_path / "result.json"
    publisher = JobResultPublisher(result_path)
    runtime = QualityRuntime(GitHub(), publisher, read_only=False)
    monkeypatch.setattr(flaky_tests_module, "execute_manifest", lambda _path: (failed,))

    with environment({"GITHUB_EVENT_PATH": str(event_path)}):
        assert flaky_tests_run_check(manifest, runtime) == 1
    first_state = fake_state()
    dashboard = state_objects(first_state, "comments")[0]
    assert "monori-qg-sticky: flaky-tests" in string_value(dashboard["body"], "body")
    assert "monori-flaky-test-failed" in array_value(first_state["labels"], "labels")
    assert read_job_result(result_path).annotations[0].path == "server/tests/test_budget.py"

    upsert_comment(GitHub(), PULL_REQUEST_NUMBER, "quality-graph", "Replaced dashboard")
    replaced = state_objects(fake_state(), "comments")[0]
    assert "monori-qg-sticky: flaky-tests" in string_value(replaced["body"], "body")

    monkeypatch.setattr(flaky_tests_module, "execute_manifest", lambda _path: (passed,))

    with environment({"GITHUB_EVENT_PATH": str(event_path)}):
        assert flaky_tests_run_check(manifest, runtime) == 1
    assert read_job_result(result_path).status is JobStatus.FAILED


def test_flaky_gate_skips_state_publication_for_a_stale_event_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Prevent an older workflow from publishing state for a newer pull-request head.
    """
    event_head = "a" * 40
    current_head = "b" * 40
    reset_fake_github(
        {
            "pulls": [
                {
                    "number": PULL_REQUEST_NUMBER,
                    "body": "Pull request body",
                    "html_url": f"https://github.com/{REPOSITORY}/pull/{PULL_REQUEST_NUMBER}",
                    "head": {"sha": current_head},
                    "base": {"sha": "base-sha"},
                }
            ]
        }
    )
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "number": PULL_REQUEST_NUMBER,
                    "head": {"sha": event_head},
                }
            }
        )
    )
    result_path = tmp_path / "result.json"
    runtime = QualityRuntime(GitHub(), JobResultPublisher(result_path), read_only=False)

    def unexpected_execution(path: Path) -> tuple[RepetitionResult, ...]:
        raise AssertionError(path)

    monkeypatch.setattr(flaky_tests_module, "execute_manifest", unexpected_execution)

    with environment({"GITHUB_EVENT_PATH": str(event_path)}):
        assert flaky_tests_run_check(tmp_path / "manifest.json", runtime) == 0

    assert read_job_result(result_path).status is JobStatus.SKIPPED
    assert array_value(fake_state()["labels"], "labels") == []


def test_flaky_gate_rechecks_the_head_after_repetitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Discard results when a new commit arrives while repetitions are running.
    """
    event_head = "a" * 40
    next_head = "b" * 40
    reset_fake_github(
        {
            "pulls": [
                {
                    "number": PULL_REQUEST_NUMBER,
                    "body": "Pull request body",
                    "html_url": f"https://github.com/{REPOSITORY}/pull/{PULL_REQUEST_NUMBER}",
                    "head": {"sha": event_head},
                    "base": {"sha": "base-sha"},
                }
            ]
        }
    )
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "number": PULL_REQUEST_NUMBER,
                    "head": {"sha": event_head},
                }
            }
        )
    )

    def push_new_head(path: Path) -> tuple[RepetitionResult, ...]:
        assert path == tmp_path / "manifest.json"
        reset_fake_github(
            {
                "pulls": [
                    {
                        "number": PULL_REQUEST_NUMBER,
                        "body": "New head body",
                        "html_url": f"https://github.com/{REPOSITORY}/pull/{PULL_REQUEST_NUMBER}",
                        "head": {"sha": next_head},
                        "base": {"sha": "base-sha"},
                    }
                ]
            }
        )
        return ()

    monkeypatch.setattr(flaky_tests_module, "execute_manifest", push_new_head)
    result_path = tmp_path / "result.json"
    runtime = QualityRuntime(GitHub(), JobResultPublisher(result_path), read_only=False)

    with environment({"GITHUB_EVENT_PATH": str(event_path)}):
        assert flaky_tests_run_check(tmp_path / "manifest.json", runtime) == 0

    assert read_job_result(result_path).status is JobStatus.SKIPPED
    pull = object_value(array_value(fake_state()["pulls"], "pulls")[0], "pull")
    assert string_value(pull["body"], "body") == "New head body"


def test_source_gate_converges_labels_and_writes_job_results(tmp_path: Path) -> None:
    """Publish red and green results without creating gate-specific comments."""
    reset_fake_github()
    github = GitHub()
    result_path = tmp_path / "result.json"
    summary_path = tmp_path / "summary.md"

    publisher = JobResultPublisher(result_path, summary_path)
    failed = ScenarioCheck([ScenarioFinding("finding-1", "example.py")])
    assert failed.run_pull_request_gate(github, pull_request_event(), publisher) == 1
    failed_result = result_path.read_text()
    assert '"status": "failed"' in failed_result
    passed = ScenarioCheck([])
    assert passed.run_pull_request_gate(github, pull_request_event(), publisher) == 0
    final_state = fake_state()
    assert final_state["issue_labels"] == {str(PULL_REQUEST_NUMBER): []}
    assert state_objects(final_state, "comments") == []
    assert '"status": "passed"' in result_path.read_text()
    assert "0 findings" in summary_path.read_text()


def test_source_gate_read_only_mode_avoids_pull_request_mutations(tmp_path: Path) -> None:
    """Evaluate fork findings without requiring labels or pull-request write access."""
    reset_fake_github(
        {
            "failures": [
                {
                    "method": "PATCH",
                    "path": f"/repos/{REPOSITORY}/pulls/{PULL_REQUEST_NUMBER}",
                    "status": HTTPStatus.FORBIDDEN,
                },
                {
                    "method": "POST",
                    "path": f"/repos/{REPOSITORY}/issues/{PULL_REQUEST_NUMBER}/labels",
                    "status": HTTPStatus.FORBIDDEN,
                },
            ]
        }
    )
    result_path = tmp_path / "result.json"

    exit_code = ScenarioCheck([ScenarioFinding("finding-1", "example.py")]).run_pull_request_gate(
        GitHub(),
        pull_request_event(),
        JobResultPublisher(result_path),
        read_only=True,
    )

    assert exit_code == 1
    assert read_job_result(result_path).status is JobStatus.FAILED


def test_bundle_and_performance_gates_publish_real_http_state(tmp_path: Path) -> None:
    """Apply report gates through files and the real HTTP client."""
    reset_fake_github()
    bundle_report = tmp_path / "bundle.json"
    bundle_summary = tmp_path / "bundle.md"
    bundle_report.write_text(
        json.dumps(
            {
                "prNumber": PULL_REQUEST_NUMBER,
                "verdict": "critical",
                "entries": [
                    {
                        "id": "bundle-initial-load",
                        "label": "Initial load",
                        "base": 1000,
                        "current": 2000,
                        "delta": 1000,
                        "percent": 100.0,
                        "tier": "critical",
                    }
                ],
                "assetGrowth": [],
            }
        )
    )
    with environment({"REPORT_PATH": str(bundle_report), "SUMMARY_PATH": str(bundle_summary)}):
        assert bundle_size_main() == 1
    assert "Initial load" in bundle_summary.read_text()

    performance_report = tmp_path / "performance.json"
    performance_summary = tmp_path / "performance.md"
    performance_report.write_text(
        json.dumps(
            {
                "prNumber": PULL_REQUEST_NUMBER,
                "verdict": "critical",
                "entries": [
                    {
                        "route_id": "dashboard",
                        "route_label": "Dashboard",
                        "metric_id": "lcp",
                        "metric_label": "LCP",
                        "tier": "critical",
                    }
                ],
            }
        )
    )
    performance_summary.write_text("## Previous heading\n\nMeasured details.\n")
    with environment(
        {"REPORT_PATH": str(performance_report), "SUMMARY_PATH": str(performance_summary)}
    ):
        assert frontend_performance_main() == 1
    assert "Dashboard · LCP" in performance_summary.read_text()
    state = fake_state()
    assert set(array_value(state["labels"], "labels")) == {
        "monori-bundle-size-failed",
        "monori-frontend-performance-failed",
    }


def test_bundle_and_performance_read_only_gates_preserve_failed_verdicts(
    tmp_path: Path,
) -> None:
    """Publish measurement failures without mutating a read-only pull request."""
    failures: JsonValue = [
        {
            "method": "PATCH",
            "path": f"/repos/{REPOSITORY}/pulls/{PULL_REQUEST_NUMBER}",
            "status": HTTPStatus.FORBIDDEN,
        },
        {
            "method": "POST",
            "path": f"/repos/{REPOSITORY}/labels",
            "status": HTTPStatus.FORBIDDEN,
        },
        {
            "method": "POST",
            "path": f"/repos/{REPOSITORY}/issues/{PULL_REQUEST_NUMBER}/labels",
            "status": HTTPStatus.FORBIDDEN,
        },
    ]
    reset_fake_github({"failures": failures})
    bundle_report = tmp_path / "bundle.json"
    bundle_summary = tmp_path / "bundle.md"
    bundle_report.write_text(
        json.dumps(
            {
                "prNumber": PULL_REQUEST_NUMBER,
                "verdict": "critical",
                "entries": [
                    {
                        "id": "bundle-initial-load",
                        "label": "Initial load",
                        "base": 1000,
                        "current": 2000,
                        "delta": 1000,
                        "percent": 100.0,
                        "tier": "critical",
                    }
                ],
                "assetGrowth": [],
            }
        )
    )
    environment_values = {
        "REPORT_PATH": str(bundle_report),
        "SUMMARY_PATH": str(bundle_summary),
        "QUALITY_GRAPH_READ_ONLY": "true",
    }
    with environment(environment_values):
        assert bundle_size_main() == 1
    assert '"verdict": "critical"' in bundle_report.read_text()

    performance_report = tmp_path / "performance.json"
    performance_summary = tmp_path / "performance.md"
    performance_report.write_text(
        json.dumps(
            {
                "prNumber": PULL_REQUEST_NUMBER,
                "verdict": "critical",
                "entries": [
                    {
                        "route_id": "dashboard",
                        "route_label": "Dashboard",
                        "metric_id": "lcp",
                        "metric_label": "LCP",
                        "tier": "critical",
                    }
                ],
            }
        )
    )
    performance_summary.write_text("## Previous heading\n\nMeasured details.\n")
    environment_values = {
        "REPORT_PATH": str(performance_report),
        "SUMMARY_PATH": str(performance_summary),
        "QUALITY_GRAPH_READ_ONLY": "true",
    }
    with environment(environment_values):
        assert frontend_performance_main() == 1
    assert '"verdict": "critical"' in performance_report.read_text()


def test_source_gate_failure_does_not_publish_a_stale_comment() -> None:
    """Leave the shared dashboard untouched when source collection raises."""
    path = f"/repos/{REPOSITORY}/pulls/{PULL_REQUEST_NUMBER}"
    reset_fake_github(
        {
            "failures": cast(
                "JsonValue",
                [{"method": "GET", "path": path, "status": SERVICE_UNAVAILABLE}],
            )
        }
    )

    with pytest.raises(GitHubAPIError):
        ScenarioCheck([]).run_pull_request_gate(
            GitHub(), pull_request_event(), JobResultPublisher()
        )

    assert state_objects(fake_state(), "comments") == []


def test_missing_pull_request_does_not_publish_a_stale_comment() -> None:
    """Leave the shared dashboard untouched when the pull request disappeared."""
    reset_fake_github({"pulls": []})

    with pytest.raises(RuntimeError, match="Pull request #7 was not found"):
        ScenarioCheck([]).run_pull_request_gate(
            GitHub(), pull_request_event(), JobResultPublisher()
        )

    assert state_objects(fake_state(), "comments") == []


def test_repository_client_surfaces_transport_failure() -> None:
    """Convert a real connection failure into the reusable client error contract."""
    with environment({"GITHUB_API_URL": "http://127.0.0.1:1"}):
        github = GitHub()
        with pytest.raises(RuntimeError, match="GitHub API GET /pulls/7 failed"):
            github.request("GET", f"/pulls/{PULL_REQUEST_NUMBER}")


def test_concrete_source_gates_scan_repository_contents_over_http() -> None:
    """Run both source gates against changed files served by the fake repository."""
    object_source = "value: object\n"
    suppression_source = "value = 1  # noqa\n"
    reset_fake_github(
        {
            "pull_files": {
                str(PULL_REQUEST_NUMBER): [
                    {
                        "filename": "example.py",
                        "status": "modified",
                        "patch": "@@ -0,0 +1 @@\n+value: object",
                    },
                    {
                        "filename": "suppressed.py",
                        "status": "modified",
                        "patch": "@@ -0,0 +1 @@\n+value = 1  # noqa",
                    },
                ]
            },
            "contents": {
                "head-sha:example.py": object_source,
                "head-sha:suppressed.py": suppression_source,
                "base-sha:example.py": "",
                "base-sha:suppressed.py": "",
            },
        }
    )

    assert object_annotations_main() == 1
    assert suppressions_main() == 1
    state = fake_state()
    labels = set(array_value(state["labels"], "labels"))
    assert "monori-object-annotation-failed" in labels
    assert "monori-suppression-failed" in labels


def test_object_gate_handles_unpatched_renames_and_skips_irrelevant_files(
    tmp_path: Path,
) -> None:
    """Compare renamed Python files when GitHub omits their patch."""
    reset_fake_github(
        {
            "pull_files": {
                str(PULL_REQUEST_NUMBER): [
                    {"filename": "removed.py", "status": "removed", "patch": ""},
                    {"filename": "README.md", "status": "modified", "patch": ""},
                    {
                        "filename": "renamed.py",
                        "previous_filename": "old.py",
                        "status": "renamed",
                    },
                ]
            },
            "contents": {
                "head-sha:renamed.py": "value: object\n",
                "base-sha:old.py": "value: str\n",
            },
        }
    )

    summary_path = tmp_path / "summary.md"
    with environment({"GITHUB_STEP_SUMMARY": str(summary_path)}):
        assert object_annotations_main() == 1
    assert "renamed.py:1" in summary_path.read_text()


def test_object_gate_reports_missing_comparison_as_infrastructure_failure() -> None:
    """Raise an infrastructure failure without overwriting the shared dashboard."""
    reset_fake_github(
        {
            "pull_files": {
                str(PULL_REQUEST_NUMBER): [
                    {"filename": "example.py", "status": "modified", "patch": ""}
                ]
            },
            "comparisons": {},
        }
    )

    with pytest.raises(RuntimeError, match="Cannot determine merge base"):
        object_annotations_main()

    assert state_objects(fake_state(), "comments") == []
