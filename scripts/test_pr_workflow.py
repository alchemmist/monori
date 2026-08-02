import re
import unittest
from pathlib import Path
from typing import ClassVar, override


WORKFLOW = Path(__file__).parents[1] / ".github/workflows/pr-checks.yml"


class PullRequestWorkflowGraphTest(unittest.TestCase):
    source: ClassVar[str]

    @override
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text()

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
                self.source, re.compile(rf"^    {re.escape(job)}:\s*$", re.MULTILINE), job
            )

    def test_checks_form_a_sequential_chain(self) -> None:
        chain = (
            ("fmt-check", "workflow-graph"),
            ("lint", "fmt-check"),
            ("type", "lint"),
            ("analyze", "type"),
            ("test-fast", "analyze"),
            ("test-medium", "test-fast"),
            ("test-slow", "test-medium"),
            ("build", "test-slow"),
            ("coverage", "build"),
            ("audit-deps", "coverage"),
            ("audit-deps-py", "audit-deps"),
            ("secrets", "audit-deps-py"),
        )
        for job, dependency in chain:
            block = re.search(
                rf"^    {re.escape(job)}:\n(?P<body>.*?)(?=^    \S|\Z)",
                self.source,
                re.MULTILINE | re.DOTALL,
            )
            self.assertIsNotNone(block, job)
            assert block is not None
            self.assertRegex(block.group("body"), rf"needs: {re.escape(dependency)}(?:\n|$)", job)
            self.assertIn(f"needs.{dependency}.result == 'success'", block.group("body"), job)

    def test_expensive_checks_start_after_secret_scan(self) -> None:
        for job in ("mutation", "bundle-size", "frontend-performance-scope"):
            block = re.search(
                rf"^    {re.escape(job)}:\n(?P<body>.*?)(?=^    \S|\Z)",
                self.source,
                re.MULTILINE | re.DOTALL,
            )
            self.assertIsNotNone(block, job)
            assert block is not None
            self.assertRegex(block.group("body"), r"needs: secrets(?:\n|$)|needs: \[secrets,", job)
            self.assertIn("needs.secrets.result == 'success'", block.group("body"), job)

    def test_code_and_api_gate_events_are_separated(self) -> None:
        self.assertIn("github.event_name == 'pull_request'", self.source)
        self.assertNotIn("github.event_name == 'pull_request_target'", self.source)
        self.assertNotIn("issue_comment:", self.source)


if __name__ == "__main__":
    unittest.main()
