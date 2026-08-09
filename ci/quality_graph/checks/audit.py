"""Audit project dependencies and security posture."""

from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.run_job import MakeCheck

CHECK = MakeCheck(WORKFLOW_JOB_BY_ID["audit"], "audit")


def main() -> int:
    """Run dependency and security audits and publish their Quality Graph result."""
    return CHECK.main()


if __name__ == "__main__":
    raise SystemExit(main())
