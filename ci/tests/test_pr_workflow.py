import re
from pathlib import Path
from typing import ClassVar, TypedDict, cast

import yaml

REPOSITORY_ROOT = Path.cwd()
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/pr-checks.yaml"
FRONTEND_PERFORMANCE_SCOPE = (
    REPOSITORY_ROOT / ".github/actions/frontend-performance-scope/action.yml"
)
ADMIN_COMMAND_ACTION = REPOSITORY_ROOT / ".github/actions/admin-command/action.yml"
REPORTING_ACTIONS = (
    "bundle-size-gate",
    "frontend-performance-gate",
    "frontend-performance-scope",
    "mutation-diff-gate",
    "object-annotation-gate",
    "suppression-gate",
)


class WorkflowJob(TypedDict, total=False):
    needs: str | list[str]


class WorkflowDocument(TypedDict):
    jobs: dict[str, WorkflowJob]


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
            "lint",
            "type",
            "analyze",
            "test-fast",
            "test-medium",
            "test-slow",
            "build",
            "coverage",
            "audit",
            "mutation",
            "bundle-size",
            "frontend-performance",
            "object-annotations",
            "suppressions",
            "admin-command",
            "quality-report",
        ):
            pattern = re.compile(rf"^    {re.escape(job)}:\s*$", re.MULTILINE)
            assert pattern.search(self.source), job

    def test_checks_have_declared_dependencies_and_no_cycle(self) -> None:
        jobs = self.workflow["jobs"]
        expected = {
            "fmt-check": "workflow-graph",
            "suppressions": "fmt-check",
            "lint": "suppressions",
            "object-annotations": "fmt-check",
            "type": "object-annotations",
            "analyze": {"lint", "type"},
            "test-fast": "analyze",
            "test-medium": "analyze",
            "test-slow": {"test-fast", "test-medium"},
            "coverage": "test-slow",
            "mutation": "test-slow",
            "build": "test-slow",
            "bundle-size": "build",
            "frontend-performance": "build",
        }
        for job, dependency in expected.items():
            data = jobs[job]
            needs = data.get("needs", [])
            needs = [needs] if isinstance(needs, str) else needs
            expected_needs = dependency if isinstance(dependency, set) else {dependency}
            assert set(needs) == expected_needs, job

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

    def test_final_audits_converge_after_all_expensive_checks(self) -> None:
        jobs = self.workflow["jobs"]
        expected_dependencies = {
            "audit": {"coverage", "mutation", "bundle-size", "frontend-performance"},
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
            assert "always()" in block.group("body"), job
            assert "needs.frontend-performance.result == 'success'" in block.group("body"), job

    def test_complex_gates_use_local_actions(self) -> None:
        expected_actions = {
            "mutation": "mutation-diff-gate",
            "bundle-size": "bundle-size-gate",
            "frontend-performance": "frontend-performance-gate",
            "object-annotations": "object-annotation-gate",
            "suppressions": "suppression-gate",
            "admin-command": "admin-command",
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

    def test_jobs_request_only_their_python_dependency_profile(self) -> None:
        """Install job-specific Python tooling instead of the aggregate dev environment."""
        expected = {
            "workflow-graph": "ci",
            "fmt-check": "format",
            "lint": "lint",
            "type": "type",
            "analyze": "analyze",
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

    def test_frontend_performance_is_one_conditional_job(self) -> None:
        block = re.search(
            r"^    frontend-performance:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert block is not None
        assert "uses: ./.github/actions/frontend-performance-scope" in block.group("body")
        assert "if: steps.scope.outputs.relevant == 'true'" in block.group("body")
        assert "frontend-performance-skipped" not in self.source

    def test_frontend_performance_scope_covers_the_gate_implementation(self) -> None:
        scope_source = FRONTEND_PERFORMANCE_SCOPE.read_text()

        assert '"ci/quality_graph/checks/frontend_performance.py"' in scope_source
        assert '"ci/tests/test_frontend_performance.py"' in scope_source

    def test_reporting_actions_publish_portable_results(self) -> None:
        for action in REPORTING_ACTIONS:
            source = (REPOSITORY_ROOT / f".github/actions/{action}/action.yml").read_text()
            assert "quality-result-" in source, action
            assert "actions/upload-artifact@v7" in source, action

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
        assert "make-target: audit" in block.group("body")

    def test_final_dashboard_runs_after_the_complete_graph(self) -> None:
        """Collect all result artifacts even when an earlier check failed."""
        block = re.search(
            r"^    quality-report:\n(?P<body>.*?)(?=^    \S|\Z)",
            self.source,
            re.MULTILINE | re.DOTALL,
        )
        assert block is not None
        body = block.group("body")
        assert "needs: audit" in body
        assert "if: always()" in body
        assert "actions/download-artifact@v8" in body
        assert "monori.ci.quality_graph.dashboard finish" in body

    def test_code_and_api_gate_events_are_separated(self) -> None:
        assert "github.event_name == 'pull_request'" in self.source
        assert "github.event_name == 'pull_request_target'" not in self.source
        assert "issue_comment:" in self.source
        assert "types: [created, edited]" in self.source
        assert "monori-qg-control:" in self.source
        assert "github.event.sender.type != 'Bot'" in self.source
