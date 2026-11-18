"""
Enforce readable delimiter lines for changed Python strings.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import tokenize
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import anyio

BASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
STRING_START_RE = re.compile(
    r"^(?:r|u|b|f|br|rb|fr|rf)?(?P<delimiter>'''|\"\"\")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    """
    Describe one triple-quote style violation.
    """

    path: str
    line: int
    column: int
    delimiter: str
    position: DelimiterPosition

    @property
    def diagnostic(self) -> str:
        """
        Render the finding in the repository source-diagnostic format.
        """
        if self.position is DelimiterPosition.INLINE:
            return (
                f"{self.path}:{self.line}:{self.column}: "
                "One-line triple-quoted string must use ordinary quotes"
            )
        return (
            f"{self.path}:{self.line}:{self.column}: Triple-quoted multiline string must "
            f"{self.position} with `{self.delimiter}` on a content-free line"
        )


class DelimiterPosition(StrEnum):
    """
    Name the delimiter position used in a style diagnostic.
    """

    OPENING = "start"
    CLOSING = "end"
    INLINE = "be replaced"


@dataclass(frozen=True)
class StringSpan:
    """
    Store source locations for one multiline triple-quoted string.
    """

    path: str
    start_line: int
    start_column: int
    opening_end: int
    end_line: int
    closing_start: int
    delimiter: str


def added_python_lines(patch: str) -> dict[str, frozenset[int]]:
    """
    Return added destination lines for every changed Python file in a patch.
    """
    path: str | None = None
    line_number: int | None = None
    result: dict[str, set[int]] = {}
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            path = None
            line_number = None
            continue
        if line_number is None and line.startswith("+++ b/"):
            candidate = line[6:]
            path = candidate if Path(candidate).suffix.lower() == ".py" else None
            if path is not None:
                result.setdefault(path, set())
            continue
        if match := HUNK_RE.match(line):
            line_number = int(match.group(1))
            continue
        if path is None or line_number is None or line.startswith("\\ No newline"):
            continue
        if line.startswith("+"):
            result[path].add(line_number)
            line_number += 1
        elif not line.startswith("-"):
            line_number += 1
    return {path: frozenset(lines) for path, lines in result.items() if lines}


def scan_source(path: str, source: str, added_lines: frozenset[int]) -> tuple[Finding, ...]:
    """
    Find changed triple-quoted strings that violate the project layout.
    """
    findings: list[Finding] = []
    source_lines = source.splitlines()
    fstrings: list[tuple[tokenize.TokenInfo, str | None]] = []
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in tokens:
        if token.type == tokenize.FSTRING_START:
            match = STRING_START_RE.match(token.string)
            delimiter = match.group("delimiter") if match is not None else None
            fstrings.append((token, delimiter))
            continue
        if token.type == tokenize.FSTRING_END:
            start, delimiter = fstrings.pop()
            if delimiter is not None:
                findings.extend(
                    _findings(
                        StringSpan(
                            path,
                            start.start[0],
                            start.end[1] - len(delimiter),
                            start.end[1],
                            token.end[0],
                            token.end[1] - len(delimiter),
                            delimiter,
                        ),
                        source_lines,
                        added_lines,
                    )
                )
            continue
        if token.type == tokenize.STRING:
            match = STRING_START_RE.match(token.string)
            if match is not None:
                delimiter = match.group("delimiter")
                findings.extend(
                    _findings(
                        StringSpan(
                            path,
                            token.start[0],
                            token.start[1] + match.start("delimiter"),
                            token.start[1] + match.end(),
                            token.end[0],
                            token.end[1] - len(delimiter),
                            delimiter,
                        ),
                        source_lines,
                        added_lines,
                    )
                )
    return tuple(findings)


def _findings(
    span: StringSpan,
    source_lines: list[str],
    added_lines: frozenset[int],
) -> tuple[Finding, ...]:
    """
    Return delimiter findings for one multiline string span.
    """
    if span.start_line == span.end_line:
        return (
            (
                Finding(
                    span.path,
                    span.start_line,
                    span.start_column + 1,
                    span.delimiter,
                    DelimiterPosition.INLINE,
                ),
            )
            if span.start_line in added_lines
            else ()
        )
    findings: list[Finding] = []
    opening_line = source_lines[span.start_line - 1]
    if span.start_line in added_lines and opening_line[span.opening_end :].strip():
        findings.append(
            Finding(
                span.path,
                span.start_line,
                span.start_column + 1,
                span.delimiter,
                DelimiterPosition.OPENING,
            )
        )
    closing_line = source_lines[span.end_line - 1]
    if span.end_line in added_lines and closing_line[: span.closing_start].strip():
        findings.append(
            Finding(
                span.path,
                span.end_line,
                span.closing_start + 1,
                span.delimiter,
                DelimiterPosition.CLOSING,
            )
        )
    return tuple(findings)


def validated_base(value: str) -> str:
    """
    Return a safe Git base ref used for diff calculation.
    """
    if not BASE_RE.fullmatch(value):
        message = f"Invalid base ref: {value}"
        raise ValueError(message)
    return value


async def patch_for_base(base: str) -> str:
    """
    Read the zero-context pull-request patch from Git.
    """
    completed = await anyio.run_process(
        (
            "git",
            "diff",
            "--unified=0",
            "--no-ext-diff",
            "--diff-filter=ACMR",
            f"{validated_base(base)}...HEAD",
            "--",
            "*.py",
        ),
        check=True,
    )
    return completed.stdout.decode()


def scan_repository(base: str) -> tuple[Finding, ...]:
    """
    Scan changed Python files in the current repository.
    """
    changed = added_python_lines(anyio.run(patch_for_base, validated_base(base)))
    return tuple(
        finding
        for path, lines in sorted(changed.items())
        for finding in scan_source(path, Path(path).read_text(), lines)
    )


def main() -> int:
    """
    Run the changed-line checker and return a blocking style verdict.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args()
    findings = scan_repository(args.base)
    if findings:
        sys.stdout.write("\n".join(finding.diagnostic for finding in findings) + "\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
