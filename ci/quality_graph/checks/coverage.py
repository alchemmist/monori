"""Measure project test coverage."""

from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.run_job import MakeCheck

CHECK = MakeCheck(WORKFLOW_JOB_BY_ID["coverage"], "coverage-diff")


def main() -> int:
    """Collect coverage and publish its Quality Graph result."""
    return CHECK.main()


if __name__ == "__main__":
    raise SystemExit(main())
