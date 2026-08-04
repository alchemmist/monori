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
    """Citation for why a vulnerability is present and its severity context."""

    severity: str = ""
    url: str = ""
    title: str = ""


@pydantic_dataclass(config=ConfigDict(extra="ignore"))
class AuditNode:
    """Vulnerability record in npm audit payload."""

    via: list[str | AuditVia]


@pydantic_dataclass(config=ConfigDict(extra="ignore"))
class AuditError:
    """Error metadata returned by npm audit."""

    code: str = "unknown"
    summary: str = ""


@pydantic_dataclass(config=ConfigDict(extra="ignore"))
class AuditPayload:
    """Top-level npm audit JSON payload shape."""

    error: AuditError | None = None
    vulnerabilities: dict[str, AuditNode] | None = None


AUDIT_PAYLOAD_ADAPTER: TypeAdapter[AuditPayload] = TypeAdapter(AuditPayload)

ALLOWED = {
    "GHSA-qwww-vcr4-c8h2": "react-router RSC-only; N/A to our SPA, no fix released",
}


def main() -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    data = AUDIT_PAYLOAD_ADAPTER.validate_python(json.load(sys.stdin))
    if data.error is not None or data.vulnerabilities is None:
        err = data.error
        code = err.code if err else "unknown"
        summary = err.summary if err else "missing vulnerabilities"
        print(
            f"npm-audit-gate [FAIL]: npm audit did not run — {code}: {summary}",
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
