"""Detect plausible Unix timestamps introduced on changed source lines."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import anyio

from monori.ci.lib.findings import stable_finding_id

SOURCE_SUFFIXES = frozenset({".cjs", ".js", ".jsx", ".mjs", ".py", ".sh", ".sql", ".ts", ".tsx"})
BASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
NUMBER_RE = re.compile(r"(?<![\w.])\d(?:_?\d){8,18}(?![\w.])")
TIMESTAMP_SCALES = (
    ("nanoseconds", 10**9),
    ("microseconds", 10**6),
    ("milliseconds", 10**3),
    ("seconds", 1),
)
EARLIEST_SECONDS = 9_466_848 * 100
LATEST_SECONDS = 72_581_184 * 100


@dataclass(frozen=True)
class Finding:
    """Describe one plausible Unix timestamp on an added source line."""

    path: str
    line: int
    column: int
    literal: str
    unit: str
    finding_id: str


def eligible_path(path: str) -> bool:
    """Return whether a path contains executable source or test code."""
    return Path(path).suffix.lower() in SOURCE_SUFFIXES


def parse_added_lines(patch: str) -> tuple[tuple[str, int, str], ...]:
    """Extract added source lines and their destination line numbers from a Git patch."""
    path: str | None = None
    line_number: int | None = None
    added: list[tuple[str, int, str]] = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            path = None
            line_number = None
            continue
        if line_number is None and line.startswith("+++ b/"):
            candidate = line[6:]
            path = candidate if eligible_path(candidate) else None
            continue
        if match := HUNK_RE.match(line):
            line_number = int(match.group(1))
            continue
        if path is None or line_number is None or line.startswith("\\ No newline"):
            continue
        if line.startswith("+"):
            added.append((path, line_number, line[1:]))
            line_number += 1
        elif not line.startswith("-"):
            line_number += 1
    return tuple(added)


def timestamp_unit(literal: str) -> str | None:
    """Classify a plausible Unix timestamp literal by its unit."""
    value = int(literal.replace("_", ""))
    for unit, scale in TIMESTAMP_SCALES:
        if EARLIEST_SECONDS * scale <= value <= LATEST_SECONDS * scale:
            return unit
    return None


def scan_patch(patch: str) -> tuple[Finding, ...]:
    """Find plausible Unix timestamp literals on added source lines."""
    findings: list[Finding] = []
    for path, line_number, source in parse_added_lines(patch):
        for match in NUMBER_RE.finditer(source):
            literal = match.group()
            unit = timestamp_unit(literal)
            if unit is None:
                continue
            raw_id = f"{path}:{source.strip()}:{literal}:{match.start()}"
            findings.append(
                Finding(
                    path,
                    line_number,
                    match.start() + 1,
                    literal,
                    unit,
                    stable_finding_id(raw_id),
                )
            )
    return tuple(findings)


def validated_base(value: str) -> str:
    """Return a safe Git base ref used for local and CI diff calculation."""
    if not BASE_RE.fullmatch(value):
        message = f"Invalid base ref: {value}"
        raise ValueError(message)
    return value


def patch_for_base(base: str) -> str:
    """Return a zero-context patch against the selected merge base."""
    return anyio.run(_patch_for_base, validated_base(base))


async def _patch_for_base(base: str) -> str:
    completed = await anyio.run_process(
        (
            "git",
            "diff",
            "--unified=0",
            "--no-ext-diff",
            "--diff-filter=ACMR",
            f"{validated_base(base)}...HEAD",
            "--",
        ),
        check=True,
    )
    return completed.stdout.decode()


def diagnostic(finding: Finding) -> str:
    """Render one finding in the shared source-diagnostic format."""
    return (
        f"{finding.path}:{finding.line}:{finding.column}: warning: "
        f"possible Unix timestamp in {finding.unit}: {finding.literal}"
    )


def main() -> int:
    """Scan a local branch against its base and print source diagnostics."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args()
    findings = scan_patch(patch_for_base(args.base))
    if findings:
        sys.stdout.write("\n".join(diagnostic(finding) for finding in findings) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
