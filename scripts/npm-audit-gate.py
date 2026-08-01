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

from pydantic import ConfigDict, TypeAdapter
from pydantic.dataclasses import dataclass as pydantic_dataclass

BLOCKING = {"high", "critical"}


@pydantic_dataclass(config=ConfigDict(extra="ignore"))
class AuditVia:
    severity: str = ""
    url: str = ""
    title: str = ""


@pydantic_dataclass(config=ConfigDict(extra="ignore"))
class AuditNode:
    via: list[str | AuditVia]


@pydantic_dataclass(config=ConfigDict(extra="ignore"))
class AuditError:
    code: str = "unknown"
    summary: str = ""


@pydantic_dataclass(config=ConfigDict(extra="ignore"))
class AuditPayload:
    error: AuditError | None = None
    vulnerabilities: dict[str, AuditNode] | None = None


AUDIT_PAYLOAD_ADAPTER: TypeAdapter[AuditPayload] = TypeAdapter(AuditPayload)

# GHSA id -> reason it is knowingly tolerated. Keep this list short and revisit
# whenever `npm audit` output changes.
ALLOWED = {
    # RSC Mode CSRF: only affects React Router's React Server Components mode.
    # We ship a Vite SPA (client/data mode, no RSC), and no fixed react-router
    # is published yet (7.18.1 is the latest 7.x and the whole line is in range).
    "GHSA-qwww-vcr4-c8h2": "react-router RSC-only; N/A to our SPA, no fix released",
}


def main() -> int:
    data = AUDIT_PAYLOAD_ADAPTER.validate_python(json.load(sys.stdin))
    # npm audit could not run (e.g. ENOLOCK with no lockfile) — it returns an
    # error payload with no vulnerabilities data. Fail loudly rather than let an
    # audit that never happened read as a clean pass.
    if data.error is not None or data.vulnerabilities is None:
        err = data.error
        print(
            "npm-audit-gate [FAIL]: npm audit did not run — "
            f"{err.code if err else 'unknown'}: {err.summary if err else 'missing vulnerabilities'}",
            file=sys.stderr,
        )
        return 1
    blocking: list[str] = []
    for name, vuln in data.vulnerabilities.items():
        for via in vuln.via:
            if isinstance(via, str):
                continue
            if via.severity not in BLOCKING:
                continue
            url = via.url
            ghsa = url.rsplit("/", 1)[-1]
            if ghsa in ALLOWED:
                print(f"npm-audit-gate: allowing {ghsa} ({name}) — {ALLOWED[ghsa]}")
                continue
            blocking.append(f"{via.severity}: {name} — {via.title} ({url})")

    if blocking:
        print("npm-audit-gate [FAIL]: blocking advisories:", file=sys.stderr)
        for line in sorted(set(blocking)):
            print(f"  {line}", file=sys.stderr)
        return 1
    print("npm-audit-gate [PASS]: no blocking advisories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
