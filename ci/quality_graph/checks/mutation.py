"""Publish the combined frontend and Python mutation result."""

from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.result_cli import publish_result_main

DEFINITION = WORKFLOW_JOB_BY_ID["mutation"]


def main() -> int:
    """Publish the specialized mutation result through its registered identity."""
    return publish_result_main(DEFINITION)


if __name__ == "__main__":
    raise SystemExit(main())
