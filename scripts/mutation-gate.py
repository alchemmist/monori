#!/usr/bin/env python3
import json
import sys


def main() -> int:
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

    killed = int(s.get("killed", 0))
    survived = int(s.get("survived", 0))
    timeout = int(s.get("timeout", 0))
    suspicious = int(s.get("suspicious", 0))

    considered = killed + survived + timeout + suspicious
    if considered == 0:
        print("mutation-gate: no mutants were tested — nothing to score", file=sys.stderr)
        return 2

    score = 100.0 * killed / considered
    status = "PASS" if score >= threshold else "FAIL"
    total = int(s.get("total", considered))
    no_tests = int(s.get("no_tests", 0))
    skipped = int(s.get("skipped", 0))
    segfault = int(s.get("segfault", 0))
    interrupted = int(s.get("check_was_interrupted_by_user", 0))

    print("── backend mutation summary ─────────────────────────")
    print("status        count   included in gate")
    print(f"killed        {killed:5}   yes")
    print(f"survived      {survived:5}   yes")
    print(f"timeout       {timeout:5}   yes")
    print(f"suspicious    {suspicious:5}   yes")
    print(f"no tests      {no_tests:5}   no")
    print(f"skipped       {skipped:5}   no")
    print(f"segfault      {segfault:5}   no")
    print(f"interrupted   {interrupted:5}   no")
    print(f"gate total    {considered:5}   killed + survived + timeout + suspicious")
    print(f"all results   {total:5}")
    print(
        f"mutation-gate [{status}]: score {score:.2f}% "
        f"(killed {killed}/{considered}, threshold {threshold:.0f}%)"
    )
    return 0 if score >= threshold else 1


if __name__ == "__main__":
    sys.exit(main())
