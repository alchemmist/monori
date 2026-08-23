"""
Run the triple-quoted string style check.
"""

from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.run_job import MakeCheck

CHECK = MakeCheck(WORKFLOW_JOB_BY_ID["triple-quotes"], "triple-quotes")


def main() -> int:
    """
    Publish the check through the shared Quality Graph lifecycle.
    """
    return CHECK.main()


if __name__ == "__main__":
    raise SystemExit(main())
