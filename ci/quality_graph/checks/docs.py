"""Validate documentation links and executable examples."""

from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.run_job import MakeCheck

CHECK = MakeCheck(WORKFLOW_JOB_BY_ID["docs"], "docs")


def main() -> int:
    """Run documentation checks and publish their Quality Graph result."""
    return CHECK.main()


if __name__ == "__main__":
    raise SystemExit(main())
