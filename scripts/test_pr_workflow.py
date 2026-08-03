import re
import unittest
from pathlib import Path
from typing import ClassVar, override

import yaml

WORKFLOW = Path(__file__).parents[1] / ".github/workflows/pr-checks.yml"


class PullRequestWorkflowGraphTest(unittest.TestCase):
    source: ClassVar[str]
    workflow: ClassVar[dict[str, object]]

    @override
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text()
        cls.workflow = yaml.safe_load(cls.source)

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
            "audit-deps",
            "audit-deps-py",
            "secrets",
            "mutation",
            "bundle-size",
            "frontend-performance-scope",
            "frontend-performance",
            "frontend-performance-skipped",
            "object-annotations",
            "suppressions",
        ):
            self.assertRegex(
                self.source,
                re.compile(rf"^    {re.escape(job)}:\s*$", re.MULTILINE),
                job,
            )

    def test_checks_have_declared_dependencies_and_no_cycle(self) -> None:
        jobs = self.workflow["jobs"]
        self.assertIsInstance(jobs, dict)
        assert isinstance(jobs, dict)
        expected = {
            "fmt-check": "workflow-graph",
            "suppressions": "fmt-check",
            "lint": "suppressions",
            "object-annotations": "lint",
            "type": "object-annotations",
            "coverage": "build",
        }
        for job, dependency in expected.items():
            data = jobs[job]
            self.assertIsInstance(data, dict)
            assert isinstance(data, dict)
            needs = data.get("needs", [])
            needs = [needs] if isinstance(needs, str) else needs
            self.assertIn(dependency, needs, job)

        dependencies: dict[str, list[str]] = {}
        for job, data in jobs.items():
            self.assertIsInstance(data, dict)
            assert isinstance(data, dict)
            needs = data.get("needs", [])
            dependencies[job] = [needs] if isinstance(needs, str) else list(needs)
            for dependency in dependencies[job]:
                self.assertIn(dependency, jobs, f"{job} needs unknown job {dependency}")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(job: str) -> None:
            if job in visiting:
                self.fail(f"workflow graph contains a cycle at {job}")
            if job in visited:
                return
            visiting.add(job)
            for dependency in dependencies[job]:
                visit(dependency)
            visiting.remove(job)
            visited.add(job)

        for job in jobs:
            visit(job)

    def test_expensive_checks_start_after_secret_scan(self) -> None:
        for job in ("mutation", "bundle-size", "frontend-performance-scope"):
            block = re.search(
                rf"^    {re.escape(job)}:\n(?P<body>.*?)(?=^    \S|\Z)",
                self.source,
                re.MULTILINE | re.DOTALL,
            )
            self.assertIsNotNone(block, job)
            assert block is not None
            self.assertRegex(
                block.group("body"), r"needs: secrets(?:\n|$)|needs: \[secrets,", job
            )
            self.assertIn("needs.secrets.result == 'success'", block.group("body"), job)

    def test_code_and_api_gate_events_are_separated(self) -> None:
        self.assertIn("github.event_name == 'pull_request'", self.source)
        self.assertNotIn("github.event_name == 'pull_request_target'", self.source)
        self.assertNotIn("issue_comment:", self.source)


if __name__ == "__main__":
    unittest.main()
