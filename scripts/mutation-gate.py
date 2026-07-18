#!/usr/bin/env python3
import json
import sys


def main():
    if len(sys.argv) != 3:
        print("usage: mutation-gate.py <cicd-stats.json> <threshold>", file=sys.stderr)
        return 2

    stats_path, threshold = sys.argv[1], float(sys.argv[2])

    try:
        with open(stats_path) as f:
            s = json.load(f)
    except FileNotFoundError:
        print(f"mutation-gate: stats file not found: {stats_path}", file=sys.stderr)
        return 2

    killed = s.get("killed", 0)
    survived = s.get("survived", 0)
    timeout = s.get("timeout", 0)
    suspicious = s.get("suspicious", 0)

    considered = killed + survived + timeout + suspicious
    if considered == 0:
        print("mutation-gate: no mutants were tested — nothing to score", file=sys.stderr)
        return 2

    score = 100.0 * killed / considered
    status = "PASS" if score >= threshold else "FAIL"
    print(
        f"mutation-gate [{status}]: score {score:.2f}% "
        f"(killed {killed}/{considered}, threshold {threshold:.0f}%)"
    )
    return 0 if score >= threshold else 1


if __name__ == "__main__":
    sys.exit(main())
