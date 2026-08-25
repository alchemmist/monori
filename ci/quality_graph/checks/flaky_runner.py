"""
Run flaky-test repetitions without repository-host publication.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from monori.ci.quality_graph.checks.flaky_tests import execute_manifest


def main() -> int:
    """
    Return failure when any discovered test is unstable.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    executions = execute_manifest(parser.parse_args().manifest)
    return int(any(execution.unstable for execution in executions))


if __name__ == "__main__":
    raise SystemExit(main())
