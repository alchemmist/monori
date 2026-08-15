#!/usr/bin/env python3
"""
Mutation gate for mutmut mutation testing results.

This module reads a JSON summary produced by mutation testing, computes a gate
score, and returns a non-zero exit code when the score is below the configured
threshold.
"""

import json
import logging
import sys
from pathlib import Path

EXPECTED_ARGC = 3
logger = logging.getLogger(__name__)


def main() -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) != EXPECTED_ARGC:
        logger.error("usage: mutation-gate.py <cicd-stats.json> <threshold>")
        return 2

    stats_path, threshold = sys.argv[1], float(sys.argv[2])

    try:
        with Path(stats_path).open() as f:
            s = json.load(f)
    except FileNotFoundError:
        logger.exception("mutation-gate: stats file not found: %s", stats_path)
        return 2

    killed = int(s.get("killed", 0))
    survived = int(s.get("survived", 0))
    timeout = int(s.get("timeout", 0))
    suspicious = int(s.get("suspicious", 0))

    considered = killed + survived + timeout + suspicious
    if considered == 0:
        logger.error("mutation-gate: no mutants were tested — nothing to score")
        return 2

    score = 100.0 * killed / considered
    status = "PASS" if score >= threshold else "FAIL"
    total = int(s.get("total", considered))
    no_tests = int(s.get("no_tests", 0))
    skipped = int(s.get("skipped", 0))
    segfault = int(s.get("segfault", 0))
    interrupted = int(s.get("check_was_interrupted_by_user", 0))

    logger.info("── Python mutation summary ─────────────────────────")
    logger.info("status        count   included in gate")
    logger.info("killed        %5s   yes", killed)
    logger.info("survived      %5s   yes", survived)
    logger.info("timeout       %5s   yes", timeout)
    logger.info("suspicious    %5s   yes", suspicious)
    logger.info("no tests      %5s   no", no_tests)
    logger.info("skipped       %5s   no", skipped)
    logger.info("segfault      %5s   no", segfault)
    logger.info("interrupted   %5s   no", interrupted)
    logger.info("gate total    %5s   killed + survived + timeout + suspicious", considered)
    logger.info("all results   %5s", total)
    logger.info(
        "mutation-gate [%s]: score %.2f%% (killed %s/%s, threshold %.0f%%)",
        status,
        score,
        killed,
        considered,
        threshold,
    )
    return 0 if score >= threshold else 1


if __name__ == "__main__":
    sys.exit(main())
