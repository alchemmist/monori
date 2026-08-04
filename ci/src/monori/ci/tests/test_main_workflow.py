import unittest
from pathlib import Path
from typing import ClassVar, cast, override

import yaml

from monori.ci.tests.test_pr_workflow import WorkflowDocument

WORKFLOW = Path(__file__).parents[3] / ".github/workflows/main-checks.yaml"


class MainWorkflowGraphTest(unittest.TestCase):
    source: ClassVar[str]
    workflow: ClassVar[WorkflowDocument]

    @override
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text()
        cls.workflow = cast("WorkflowDocument", yaml.safe_load(cls.source))

    def test_main_checks_are_individual_jobs(self) -> None:
        assert "matrix:" not in self.source
        assert "${{ matrix." not in self.source
        assert set(self.workflow["jobs"]) == {
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
            "mutation-full",
        }

    def test_main_checks_form_a_sequential_graph(self) -> None:
        jobs = self.workflow["jobs"]
        expected = {
            "lint": "fmt-check",
            "type": "lint",
            "analyze": "type",
            "test-fast": "analyze",
            "test-medium": "test-fast",
            "test-slow": "test-medium",
            "build": "test-slow",
            "coverage": "build",
            "audit": "coverage",
            "mutation-full": "audit",
        }
        for job, dependency in expected.items():
            needs = jobs[job].get("needs", [])
            needs = [needs] if isinstance(needs, str) else needs
            assert dependency in needs


if __name__ == "__main__":
    unittest.main()
