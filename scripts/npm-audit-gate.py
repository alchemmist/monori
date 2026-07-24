#!/usr/bin/env python3
"""
Fail on any high/critical npm advisory except a small allow-list of ones that
have no available fix and do not apply to how we ship the dependency. Reads
``npm audit --json`` on stdin (``npm audit`` exits non-zero when it finds
anything, so the Makefile pipes it through this gate instead of trusting the
exit code directly).
"""

import json
import sys

BLOCKING = {"high", "critical"}

# GHSA id -> reason it is knowingly tolerated. Keep this list short and revisit
# whenever `npm audit` output changes.
ALLOWED = {
    # RSC Mode CSRF: only affects React Router's React Server Components mode.
    # We ship a Vite SPA (client/data mode, no RSC), and no fixed react-router
    # is published yet (7.18.1 is the latest 7.x and the whole line is in range).
    "GHSA-qwww-vcr4-c8h2": "react-router RSC-only; N/A to our SPA, no fix released",
}


def main():
    data = json.load(sys.stdin)
    blocking = []
    for name, vuln in data.get("vulnerabilities", {}).items():
        for via in vuln.get("via", []):
            if not isinstance(via, dict):
                continue
            if via.get("severity") not in BLOCKING:
                continue
            url = via.get("url", "")
            ghsa = url.rsplit("/", 1)[-1]
            if ghsa in ALLOWED:
                print(f"npm-audit-gate: allowing {ghsa} ({name}) — {ALLOWED[ghsa]}")
                continue
            blocking.append(f"{via.get('severity')}: {name} — {via.get('title')} ({url})")

    if blocking:
        print("npm-audit-gate [FAIL]: blocking advisories:", file=sys.stderr)
        for line in sorted(set(blocking)):
            print(f"  {line}", file=sys.stderr)
        return 1
    print("npm-audit-gate [PASS]: no blocking advisories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
