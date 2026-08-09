"""Check repository formatting."""

from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.run_job import MakeCheck

CHECK = MakeCheck(WORKFLOW_JOB_BY_ID["fmt-check"], "fmt-check", "fmt")


def main() -> int:
    """Run formatting checks and publish their Quality Graph result."""
    return CHECK.main()


if __name__ == "__main__":
    raise SystemExit(main())
