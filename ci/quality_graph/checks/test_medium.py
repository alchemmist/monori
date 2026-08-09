"""Run the medium test suite."""

from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.run_job import MakeCheck

CHECK = MakeCheck(WORKFLOW_JOB_BY_ID["test-medium"], "t-medium")


def main() -> int:
    """Run medium tests and publish their Quality Graph result."""
    return CHECK.main()


if __name__ == "__main__":
    raise SystemExit(main())
