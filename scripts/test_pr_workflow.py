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
            "quality",
            "mutation",
            "bundle-size",
            "frontend-performance",
            "object-annotations",
            "suppressions",
        ):
            self.assertRegex(
                self.source, re.compile(rf"^    {re.escape(job)}:\s*$", re.MULTILINE), job
            )

    def test_expensive_checks_depend_on_quality(self) -> None:
        for job in ("mutation", "bundle-size", "frontend-performance"):
            block = re.search(
                rf"^    {re.escape(job)}:\n(?P<body>.*?)(?=^    \S|\Z)",
                self.source,
                re.MULTILINE | re.DOTALL,
            )
            self.assertIsNotNone(block, job)
            assert block is not None
            self.assertRegex(block.group("body"), r"needs: (?:quality|\[quality, workflow-graph\])", job)
            self.assertIn("needs.quality.result == 'success'", block.group("body"), job)

    def test_code_and_api_gate_events_are_separated(self) -> None:
        self.assertIn("github.event_name == 'pull_request'", self.source)
        self.assertIn("github.event_name == 'pull_request_target'", self.source)
        self.assertNotIn("issue_comment:", self.source)


if __name__ == "__main__":
    unittest.main()
