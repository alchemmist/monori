import re
import tomllib
from pathlib import Path
from typing import ClassVar, TypedDict, cast

import yaml

from monori.ci.quality_graph.checks.coverage import CHECK as COVERAGE_CHECK
from monori.ci.quality_graph.checks.coverage import CoverageResultAdapter
from monori.ci.quality_graph.dashboard import SUPPORTED_WORKFLOW_DURATION_SECONDS
from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID


def find_repository_root(path: Path) -> Path:
    """Find the checkout containing the workflow files used by these tests."""
    for parent in (path, *path.parents):
        if (parent / ".github").is_dir():
            return parent
    message = f"Cannot find repository root from {path}"
    raise RuntimeError(message)


REPOSITORY_ROOT = find_repository_root(Path(__file__).resolve())
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/pr-checks.yaml"
MAIN_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/main-checks.yaml"
ROOT_PYPROJECT = REPOSITORY_ROOT / "pyproject.toml"
TOOL_INSTALLER = REPOSITORY_ROOT / "scripts/install-tools.sh"
FRONTEND_PERFORMANCE_SCOPE = (
    REPOSITORY_ROOT / ".github/actions/frontend-performance-scope/action.yml"
)
ADMIN_COMMAND_ACTION = REPOSITORY_ROOT / ".github/actions/admin-command/action.yml"
FLAKY_TEST_ACTION = REPOSITORY_ROOT / ".github/actions/flaky-test-gate/action.yml"
MUTATION_ACTION = REPOSITORY_ROOT / ".github/actions/mutation-diff-gate/action.yml"
TEST_RUNNERS = (
    REPOSITORY_ROOT / "Makefile",
    REPOSITORY_ROOT / "scripts/ci-tests.sh",
    REPOSITORY_ROOT / "scripts/coverage-tree.sh",
    REPOSITORY_ROOT / ".github/actions/bundle-size-gate/action.yml",
    REPOSITORY_ROOT / ".github/actions/frontend-performance-gate/action.yml",
    REPOSITORY_ROOT / ".github/actions/mutation-diff-gate/action.yml",
    REPOSITORY_ROOT / ".github/actions/object-annotation-gate/action.yml",
    REPOSITORY_ROOT / ".github/actions/suppression-gate/action.yml",
)
WorkflowStep = TypedDict("WorkflowStep", {"uses": str, "with": dict[str, str]}, total=False)


WorkflowJob = TypedDict(
    "WorkflowJob",
    {
        "if": str,
        "name": str,
        "needs": str | list[str],
        "permissions": dict[str, str],
        "steps": list[WorkflowStep],
    },
    total=False,
)


class WorkflowDocument(TypedDict):
    jobs: dict[str, WorkflowJob]
    permissions: dict[str, str]


class TestPullRequestWorkflowGraph:
    source: ClassVar[str]
    workflow: ClassVar[WorkflowDocument]

    @classmethod
    def setup_class(cls) -> None:
        cls.source = WORKFLOW.read_text()
        cls.workflow = cast("WorkflowDocument", yaml.safe_load(cls.source))

    def test_pr_workflow_contains_all_gate_jobs(self) -> None:
        for job in (
            "workflow-graph",
            "fmt-check",
            "triple-quotes",
            "docs-links",
            "lint",
            "type",
            "analyze",
            "time-bombs",
            "test-fast",
            "test-medium",
            "test-slow",
            "flaky-tests",
            "build",
            "coverage",
            "audit",
            "mutation",
            "backend-performance",
            "frontend-performance-sla",
            "bundle-size",
            "frontend-performance",
            "object-annotations",
            "suppressions",
            "admin-command",
            "quality-dashboard-live",
            "quality-report",
        ):
            pattern = re.compile(rf"^    {re.escape(job)}:\s*$", re.MULTILINE)
            assert pattern.search(self.source), job

    def test_workflow_uses_job_level_write_permissions(self) -> None:
        assert self.workflow["permissions"] == {"contents": "read"}
        expected = {
            "admin-command": {
                "actions": "write",
                "contents": "read",
                "issues": "write",
                "pull-requests": "write",
            },
            "bundle-size": {
                "contents": "read",
                "issues": "write",
                "pull-requests": "write",
            },
            "frontend-performance": {
                "contents": "read",
                "issues": "write",
                "pull-requests": "write",
            },
            "flaky-tests": {
                "contents": "read",
                "issues": "write",
                "pull-requests": "write",
            },
            "object-annotations": {
                "contents": "read",
                "issues": "write",
                "pull-requests": "write",
            },
            "quality-dashboard-live": {
                "actions": "read",
                "contents": "read",
                "issues": "write",
                "pull-requests": "write",
            },
            "quality-report": {
                "actions": "read",
                "contents": "read",
                "issues": "write",
                "pull-requests": "write",
            },
            "suppressions": {
                "contents": "read",
                "issues": "write",
                "pull-requests": "write",
            },
        }
        for job, definition in self.workflow["jobs"].items():
            permissions = definition.get("permissions", {})
            if job in expected:
                assert permissions == expected[job], job
            else:
                assert "write" not in permissions.values(), job

    def test_checks_have_declared_dependencies_and_no_cycle(self) -> None:
        jobs = self.workflow["jobs"]
        expected = {
            "fmt-check": "workflow-graph",
            "suppressions": "workflow-graph",
            "triple-quotes": "workflow-graph",
            "docs-links": "workflow-graph",
            "lint": "suppressions",
            "object-annotations": "suppressions",
            "type": "object-annotations",
            "analyze": "lint",
            "time-bombs": {"analyze", "type"},
            "test-fast": "analyze",
            "test-medium": "analyze",
            "test-slow": {"test-fast", "test-medium"},
            "flaky-tests": "test-slow",
            "coverage": "test-slow",
            "mutation": "test-slow",
            "build": "test-slow",
            "backend-performance": "test-slow",
            "frontend-performance-sla": {"backend-performance", "bundle-size"},
            "bundle-size": "build",
            "frontend-performance": "frontend-performance-sla",
        }
        for job, dependency in expected.items():
            data = jobs[job]
            needs = data.get("needs", [])
            needs = [needs] if isinstance(needs, str) else needs
            expected_needs = dependency if isinstance(dependency, set) else {dependency}
            assert set(needs) == expected_needs, job

        assert jobs["build"]["name"] == "Build frontend"

        dependencies: dict[str, list[str]] = {}
        for job, data in jobs.items():
            needs = data.get("needs", [])
            dependencies[job] = [needs] if isinstance(needs, str) else list(needs)
            for dependency in dependencies[job]:
                assert dependency in jobs, f"{job} needs unknown job {dependency}"

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(job: str) -> None:
            if job in visiting:
                message = f"workflow graph contains a cycle at {job}"
                raise AssertionError(message)
            if job in visited:
                return
            visiting.add(job)
            for dependency in dependencies[job]:
                visit(dependency)
            visiting.remove(job)
            visited.add(job)

        for job in jobs:
            visit(job)

    def test_dependency_audit_follows_bundle_measurement(self) -> None:
        jobs = self.workflow["jobs"]
        expected_dependencies = {
            "audit": {"bundle-size"},
        }
        for job, expected in expected_dependencies.items():
            needs = jobs[job].get("needs", [])
            actual = {needs} if isinstance(needs, str) else set(needs)
            assert actual == expected, job

            block = re.search(
                rf"^    {re.escape(job)}:\n(?P<body>.*?)(?=^    \S|\Z)",
                self.source,
                re.MULTILINE | re.DOTALL,
            )
            assert block is not None, job
            assert "always()" not in block.group("body"), job
            assert "needs.bundle-size.result == 'success'" in block.group("body"), job

    def test_complex_gates_use_local_actions(self) -> None:
        expected_actions = {
            "mutation": "mutation-diff-gate",
            "backend-performance": "backend-performance",
            "frontend-performance-sla": "frontend-lab-performance",
            "bundle-size": "bundle-size-gate",
            "frontend-performance": "frontend-performance-gate",
            "object-annotations": "object-annotation-gate",
            "suppressions": "suppression-gate",
            "admin-command": "admin-command",
            "flaky-tests": "flaky-test-gate",
        }
        for job, action in expected_actions.items():
            block = re.search(
                rf"^    {re.escape(job)}:\n(?P<body>.*?)(?=^    \S|\Z)",
                self.source,
                re.MULTILINE | re.DOTALL,
            )
            assert block is not None, job
            assert f"uses: ./.github/actions/{action}" in block.group("body"), job

    def test_admin_command_action_does_not_run_tests_at_runtime(self) -> None:
        """Keep command handling independent from the test dependency profile."""
        source = ADMIN_COMMAND_ACTION.read_text()

        assert "Process Quality Graph command" in source
        assert "unittest" not in source
        assert "pytest" not in source

    def test_flaky_test_gate_is_a_standalone_quality_graph_action(self) -> None:
        source = FLAKY_TEST_ACTION.read_text()

        assert "monori.ci.lib.flaky_tests" in source
        assert "monori.ci.quality_graph.checks.flaky_tests" in source
        assert "make " not in source
        assert "--retries=0" not in source
        assert "quality-result-flaky-tests" in source

    def test_jobs_request_only_their_python_dependency_profile(self) -> None:
        """Install job-specific Python tooling instead of the aggregate dev environment."""
        expected = {
            "workflow-graph": "ci",
            "fmt-check": "format",
            "triple-quotes": "ci",
            "docs-links": "ci",
            "lint": "lint",
            "type": "type",
            "analyze": "analyze",
            "time-bombs": "ci",
            "test-fast": "test",
            "test-medium": "test",
            "test-slow": "test",
            "build": "ci",
            "coverage": "coverage",
            "audit": "audit",
            "quality-report": "ci",
        }
        for job, profile in expected.items():
            block = re.search(
                rf"^    {re.escape(job)}:\n(?P<body>.*?)(?=^    \S|\Z)",
                self.source,
                re.MULTILINE | re.DOTALL,
            )
            assert block is not None, job
            assert f"python-profile: {profile}" in block.group("body"), job

    def test_lychee_downloads_are_bounded(self) -> None:
        required = (
            "--connect-timeout 10",
            "--max-time 120",
            "--retry 3",
            "--retry-max-time 120",
        )
        for path in (TOOL_INSTALLER, MAIN_WORKFLOW, WORKFLOW):
            downloads = [
                line
                for line in path.read_text().splitlines()
                if "lycheeverse/lychee/releases/download" in line
            ]
            assert len(downloads) == 1, path
            assert all(option in downloads[0] for option in required), path

    def test_analysis_profile_can_publish_quality_results(self) -> None:
        """Install the shared CI package used after the analysis command finishes."""
        configuration = tomllib.loads(ROOT_PYPROJECT.read_text())

        assert "monori-ci" in configuration["dependency-groups"]["analyze"]

    def test_frontend_performance_reuses_sla_measurements(self) -> None:
        sla = self.workflow["jobs"]["frontend-performance-sla"]
        regression = self.workflow["jobs"]["frontend-performance"]
        save = next(step for step in sla["steps"] if step.get("uses") == "actions/cache/save@v5")
        restore = next(
            step for step in regression["steps"] if step.get("uses") == "actions/cache/restore@v5"
        )
        gate = next(
            step
            for step in regression["steps"]
            if step.get("uses") == "./.github/actions/frontend-performance-gate"
        )
        run_id = "${{ github.run_id }}"
        head_sha = "${{ github.event.pull_request.head.sha }}"
        cache_key = f"frontend-performance-{run_id}-{head_sha}"

        assert save["with"] == {
            "path": "reports/perf",
            "key": cache_key,
        }
        assert restore["with"] == {**save["with"], "fail-on-cache-miss": True}
        assert gate["with"] == {"current-results": "${{ github.workspace }}/reports/perf"}

    def test_frontend_regression_collects_only_the_target_branch(self) -> None:
        action = (
            REPOSITORY_ROOT / ".github/actions/frontend-performance-gate/action.yml"
        ).read_text()
        runner = (REPOSITORY_ROOT / "scripts/frontend-perf.sh").read_text()

        assert "PERF_PR_RESULTS_DIR: ${{ inputs.current-results }}" in action
        assert 'if [ -n "$PERF_PR_RESULTS_DIR" ]; then' in runner
        assert 'restore_revision pr "$PERF_PR_RESULTS_DIR"' in runner
        assert 'base_revision=$(git rev-parse "$BASE^{commit}")' in runner

    def test_frontend_performance_scope_covers_the_gate_implementation(self) -> None:
        scope_source = FRONTEND_PERFORMANCE_SCOPE.read_text()

        assert '"ci/quality_graph/checks/frontend_performance.py"' in scope_source
        assert '"ci/tests/test_frontend_performance.py"' in scope_source

    def test_reporting_actions_publish_portable_results(self) -> None:
        actions = (
            "bundle-size-gate",
            "frontend-performance-gate",
            "frontend-performance-scope",
            "mutation-diff-gate",
            "object-annotation-gate",
            "suppression-gate",
        )
        for action in actions:
            source = (REPOSITORY_ROOT / f".github/actions/{action}/action.yml").read_text()
            assert "quality-result-" in source, action
            assert "actions/upload-artifact@v7" in source, action

        quality_action = yaml.safe_load(
            (REPOSITORY_ROOT / ".github/actions/quality-job/action.yml").read_text()
        )
        command_step = quality_action["runs"]["steps"][0]
        assert "monori.ci.quality_graph.checks" in command_step["run"]
        fmt = self.workflow["jobs"]["fmt-check"]
        quality_step = next(
            step for step in fmt["steps"] if step.get("uses") == "./.github/actions/quality-job"
        )
        assert quality_step["with"] == {"check-id": "fmt-check"}

    def test_frontend_scope_failure_completes_the_pending_report(self) -> None:
        source = FRONTEND_PERFORMANCE_SCOPE.read_text()

        assert "if: always() && steps.scope.outcome == 'failure'" in source
        assert "--status fail" in source

    def test_audit_job_runs_aggregate_make_target(self) -> None:
        block = re.search(
            r"^    audit:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert block is not None
        assert "uses: ./.github/actions/quality-job" in block.group("body")
        assert "check-id: audit" in block.group("body")

    def test_final_dashboard_runs_after_the_successful_graph(self) -> None:
        """
        Collect result artifacts only after every graph branch passes.
        """
        block = re.search(
            r"^    quality-report:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert block is not None
        body = block.group("body")
        assert set(self.workflow["jobs"]["quality-report"]["needs"]) == {
            "audit",
            "coverage",
            "docs-links",
            "flaky-tests",
            "fmt-check",
            "frontend-performance",
            "mutation",
            "triple-quotes",
            "time-bombs",
        }
        condition = self.workflow["jobs"]["quality-report"]["if"]
        assert "always()" not in condition
        assert "needs.audit.result == 'success'" in condition
        assert "needs.coverage.result == 'success'" in condition
        assert "needs.docs-links.result == 'success'" in condition
        assert "needs.flaky-tests.result == 'success'" in condition
        assert "needs.fmt-check.result == 'success'" in condition
        assert "needs.frontend-performance.result == 'success'" in condition
        assert "needs.mutation.result == 'success'" in condition
        assert "needs.triple-quotes.result == 'success'" in condition
        assert "needs.time-bombs.result == 'success'" in condition
        assert "actions/download-artifact@v8" in body
        assert "pattern: quality-result-*" in body
        assert "github.run_attempt" not in body.split("path:", maxsplit=1)[0]
        assert "merge-multiple: true" not in body
        assert "continue-on-error: true" not in body
        assert "id: quality-results" in body
        assert "if: steps.quality-results.outcome == 'success'" in body
        assert "monori.ci.quality_graph.dashboard finish" in body

    def test_live_dashboard_has_one_serial_writer(self) -> None:
        """Keep parallel check jobs from replacing the shared comment body."""
        block = re.search(
            r"^    quality-dashboard-live:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert block is not None
        body = block.group("body")
        assert "needs" not in self.workflow["jobs"]["quality-dashboard-live"]
        assert "monori.ci.quality_graph.dashboard start" in body
        assert "monori.ci.quality_graph.dashboard watch" in body
        assert "update-quality-dashboard" not in self.source

    def test_read_only_pull_requests_do_not_depend_on_dashboard_writes(self) -> None:
        """Run the validation graph for fork and Dependabot PRs without write permissions."""
        graph_source = re.search(
            r"^    workflow-graph:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert graph_source is not None
        assert "dashboard start" not in graph_source.group("body")
        assert "issues: write" not in graph_source.group("body")
        assert "pull-requests: write" not in graph_source.group("body")
        for job_id in ("quality-dashboard-live", "quality-report"):
            job_source = re.search(
                rf"^    {job_id}:\n(?P<body>.*?)(?=^    \S|\Z)",
                self.source,
                re.MULTILINE | re.DOTALL,
            )
            assert job_source is not None
            assert "head.repo.full_name == github.repository" in job_source.group("body")
            assert "pull_request.user.login != 'dependabot[bot]'" in job_source.group("body")
        for job_id in (
            "bundle-size",
            "frontend-performance",
            "object-annotations",
            "suppressions",
        ):
            job_source = re.search(
                rf"^    {job_id}:\n(?P<body>.*?)(?=^    \S|\Z)",
                self.source,
                re.MULTILINE | re.DOTALL,
            )
            assert job_source is not None
            assert "QUALITY_GRAPH_READ_ONLY:" in job_source.group("body")

    def test_live_dashboard_covers_the_supported_workflow_duration(self) -> None:
        """Keep the watcher alive beyond valid workflows lasting over 45 minutes."""
        block = re.search(
            r"^    quality-dashboard-live:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert block is not None
        timeout = re.search(
            r"^        timeout-minutes: (?P<minutes>\d+)$", block.group("body"), re.MULTILINE
        )
        assert timeout is not None
        timeout_seconds = int(timeout.group("minutes")) * 60
        assert SUPPORTED_WORKFLOW_DURATION_SECONDS > 45 * 60
        assert timeout_seconds > SUPPORTED_WORKFLOW_DURATION_SECONDS

    def test_mutation_result_requires_every_gate_step_to_succeed(self) -> None:
        """Treat skipped and cancelled mutation steps as failed results."""
        source = MUTATION_ACTION.read_text()

        for step in ("mutation-test", "mutation-front", "mutation-back"):
            assert f'"${{{{ steps.{step}.outcome }}}}" = success' in source
            assert f"steps.{step}.outcome != 'success'" in source
        assert '--metric "Frontend=${{ steps.mutation-front.outcome }}"' in source
        assert '--metric "Python=${{ steps.mutation-back.outcome }}"' in source

    def test_test_runners_cannot_publish_fixture_reports(self) -> None:
        """Prevent pytest and mutmut fixtures from polluting live job summaries."""
        for path in TEST_RUNNERS:
            source = path.read_text()
            assert "env -u GITHUB_STEP_SUMMARY -u MUTATION_SUMMARY_PATH" in source, path
            if path.name == "Makefile":
                for line in source.splitlines():
                    if re.search(r"\bpytest(?:\s|$)", line):
                        assert "env -u GITHUB_STEP_SUMMARY -u MUTATION_SUMMARY_PATH" in line
        mutmut_runner = (REPOSITORY_ROOT / "scripts/mutmut.sh").read_text()
        assert (
            'env -u GITHUB_STEP_SUMMARY -u MUTATION_SUMMARY_PATH "$repository/.venv/bin/mutmut"'
            in mutmut_runner
        )

    def test_mutation_workspace_includes_test_support_files(self) -> None:
        """Keep unit tests runnable from both mutmut staging directories."""
        configuration = tomllib.loads(ROOT_PYPROJECT.read_text())
        mutmut_runner = (REPOSITORY_ROOT / "scripts/mutmut.sh").read_text()
        copied_paths = set(configuration["tool"]["mutmut"]["also_copy"])

        assert {
            ".github",
            "scripts",
            "Makefile",
            "performance",
            "tools/frontend-perf",
        } <= copied_paths
        assert 'cp -R performance "$workspace/performance"' in mutmut_runner
        assert 'cp -R tools/frontend-perf "$workspace/tools/frontend-perf"' in mutmut_runner

    def test_actions_use_the_node_24_cache_runtime(self) -> None:
        """Keep cache actions off the deprecated Node.js 20 runtime."""
        action_sources = "\n".join(
            path.read_text()
            for directory in (
                REPOSITORY_ROOT / ".github/actions",
                REPOSITORY_ROOT / ".github/workflows",
            )
            for path in directory.rglob("*.y*ml")
        )
        assert "actions/cache@v4" not in action_sources
        assert "actions/cache@v5" in action_sources

    def test_coverage_uses_the_standard_quality_graph_contract(self) -> None:
        block = re.search(
            r"^    coverage:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert block is not None
        body = block.group("body")
        assert "uses: actions/cache/restore@v5" in body
        assert "restore-keys:" not in body
        assert "Build missing main coverage baseline" not in body
        assert "git switch" not in body
        assert "make coverage-baseline" not in body
        assert "uses: ./.github/actions/quality-job" in body
        assert "check-id: coverage" in body
        assert "BASE: ${{ github.event.pull_request.base.sha }}" in body
        assert COVERAGE_CHECK.definition is WORKFLOW_JOB_BY_ID["coverage"]
        assert COVERAGE_CHECK.make_target == "coverage-diff"
        assert isinstance(COVERAGE_CHECK.result_adapter, CoverageResultAdapter)
        assert COVERAGE_CHECK.result_adapter.report_path == Path("coverage-report/report.json")
        assert "name: coverage-report" not in body
        assert "issues: write" not in body
        assert "statuses: write" not in body

    def test_code_and_api_gate_events_are_separated(self) -> None:
        assert "github.event_name == 'pull_request'" in self.source
        assert "github.event_name == 'pull_request_target'" not in self.source
        assert "issue_comment:" in self.source
        assert "types: [created, edited]" in self.source
        assert "monori-qg-control:" in self.source
        assert "github.event.sender.type != 'Bot'" in self.source
