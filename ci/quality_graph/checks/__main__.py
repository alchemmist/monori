"""Run a registered Quality Graph check by its stable identifier."""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Protocol

from monori.ci.quality_graph.registry import workflow_job_module, workflow_jobs


class CheckEntrypoint(Protocol):
    """Describe the uniform entrypoint exposed by every check module."""

    def __call__(self) -> int:
        """Run the check and return its process exit code."""
        ...


def main() -> int:
    """Resolve a check module and delegate the remaining command arguments to it."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check-id", required=True)
    args, remaining = parser.parse_known_args()
    definition = workflow_jobs().get(args.check_id)
    if definition is None:
        message = f"Unknown Quality Graph check: {args.check_id}"
        raise ValueError(message)
    module = importlib.import_module(workflow_job_module(definition))
    entrypoint: CheckEntrypoint = module.main
    sys.argv = [sys.argv[0], *remaining]
    return entrypoint()


if __name__ == "__main__":
    raise SystemExit(main())
