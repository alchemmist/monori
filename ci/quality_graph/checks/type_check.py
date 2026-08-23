"""Check static Python and TypeScript types."""

from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.run_job import MakeCheck

CHECK = MakeCheck(WORKFLOW_JOB_BY_ID["type"], "type")


def main() -> int:
    """Run type checking and publish its Quality Graph result."""
    return CHECK.main()


if __name__ == "__main__":
    raise SystemExit(main())
