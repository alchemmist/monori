"""Fail pull requests that add hardcoded web colors."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, cast

from monori.ci.lib.findings import stable_finding_id

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import Protocol

    class ChangedFile(Protocol):
        """Describe the diff data consumed by the scanner."""

        path: str
        source: str
        added_lines: frozenset[int]


FINDING_ID_PREFIX = "color-"
RESULT_PATH = Path("reports/hardcoded-colors.json")
MANIFEST_PATH = Path(".quality-graph/manifest.json")
SOURCE_SUFFIXES = (
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".html",
    ".htm",
    ".svg",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".json",
    ".jsonc",
    ".vue",
    ".svelte",
    ".astro",
)
EXCLUDED_PARTS = {
    "node_modules",
    "vendor",
    "vendors",
    "dist",
    "build",
    "coverage",
    "generated",
    "__snapshots__",
    "fixtures",
}
EXCLUDED_NAMES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
}
HEX_RE = re.compile(
    r"(?<![\w#])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|"
    r"[0-9a-fA-F]{3})(?![0-9a-fA-F])"
)
FUNCTION_RE = re.compile(
    r"(?i)(?<![-\w])(?P<name>rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\("
    r"(?P<body>[^()]*?(?:var\([^)]*\)[^()]*)*)\)"
)
NAMED_COLORS = frozenset(
    re.findall(
        r"[a-z]+",
        """aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue
    blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk
    crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki
    darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen
    darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue
    dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite
    gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
    lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
    lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen
    lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen
    magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen
    mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream
    mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid
    palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum
    powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown
    seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen
    steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow
    yellowgreen""",
    )
)
NAMED_RE = re.compile(
    r"(?i)(?<![-\w])(" + "|".join(sorted(NAMED_COLORS, key=len, reverse=True)) + r")(?![-\w])"
)


@dataclass(frozen=True)
class Finding:
    """Describe one hardcoded color literal."""

    path: str
    line: int
    column: int
    literal: str
    format: str
    context: str
    finding_id: str


def should_scan(path: str) -> bool:
    """Return whether a changed text file belongs to the scanner scope."""
    candidate = PurePosixPath(path)
    lowered = tuple(part.lower() for part in candidate.parts)
    return (
        candidate.name.lower() not in EXCLUDED_NAMES
        and not any(part in EXCLUDED_PARTS for part in lowered)
        and not candidate.name.lower().endswith((".min.js", ".min.css"))
        and candidate.suffix.lower() in SOURCE_SUFFIXES
    )


def _named_color_is_literal(line: str, start: int, end: int) -> bool:
    before = line[:start].rstrip()
    after = line[end:].lstrip()
    quoted = bool(before[-1:] in {'"', "'", "`"} and after[:1] == before[-1:])
    css_value = bool(re.search(r"(?:[:(,]|\s)\s*$", before)) and not bool(
        re.search(r"(?:const|let|var|function|class|interface|type)\s+$", before)
    )
    return quoted or css_value


def _line_matches(line: str) -> list[tuple[int, int, str, str]]:
    matches: list[tuple[int, int, str, str]] = []
    occupied: list[tuple[int, int]] = []
    for match in FUNCTION_RE.finditer(line):
        body = match.group("body")
        if not re.search(r"(?:\d|#)", body):
            continue
        matches.append((match.start(), match.end(), match.group(), match.group("name").upper()))
        occupied.append(match.span())
    for match in HEX_RE.finditer(line):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        prefix = line[max(0, match.start() - 12) : match.start()].lower()
        if (
            prefix.endswith("url(")
            or re.search(r"(?:issue|pr)\s+$", prefix)
            or re.search(r"(?:href|src)\s*=\s*[\"']$", prefix)
        ):
            continue
        matches.append((match.start(), match.end(), match.group(), "HEX"))
    for match in NAMED_RE.finditer(line):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        if _named_color_is_literal(line, match.start(), match.end()):
            matches.append((match.start(), match.end(), match.group(), "NAMED"))
    return sorted(matches)


def scan_file(path: str, source: str, added_lines: set[int]) -> list[Finding]:
    """Scan added lines in one supported source file."""
    if not should_scan(path):
        return []
    findings: list[Finding] = []
    for line_number, line in enumerate(source.splitlines(), 1):
        if line_number not in added_lines:
            continue
        for start, _, literal, color_format in _line_matches(line):
            raw_id = f"{path}:{line_number}:{start}:{literal.lower()}"
            findings.append(
                Finding(
                    path,
                    line_number,
                    start,
                    literal,
                    color_format,
                    line.strip(),
                    f"{FINDING_ID_PREFIX}{stable_finding_id(raw_id)}",
                )
            )
    return findings


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("`", "\\`").replace("\n", " ")


def summary_body(findings: list[Finding]) -> str:
    """Build the hardcoded-color Job Summary."""
    rows = [
        "| File | Line | Literal | Format | Context | Status |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| `{_cell(finding.path)}` | {finding.line} | `{_cell(finding.literal)}` | "
        f"{finding.format} | `{_cell(finding.context[:200])}` | "
        "active |"
        for finding in findings
    )
    if not findings:
        return "No hardcoded colors found."
    ids = ",".join(finding.finding_id for finding in findings)
    files = "\n".join(
        f"- `/qg ignore-file {path}`" for path in sorted({finding.path for finding in findings})
    )
    controls = (
        f"\n\nApprove findings with `/qg ignore {ids}` or `/qg ignore hardcoded-colors`.\n{files}"
    )
    return "\n".join(rows) + controls


def result_value(
    findings: list[Finding], environment: Mapping[str, str], graph_digest: str
) -> dict[str, object]:
    """Serialize findings through the Quality Graph native Result Protocol."""
    locations = [
        {
            "path": finding.path,
            "startLine": finding.line,
            "endLine": finding.line,
            "startColumn": finding.column + 1,
            "endColumn": finding.column + len(finding.literal),
        }
        for finding in findings
    ]
    controls: list[dict[str, object]] = [
        {"kind": "finding", "target": finding.finding_id, "checked": False} for finding in findings
    ]
    controls.extend(
        {"kind": "file", "target": path, "checked": False}
        for path in sorted({finding.path for finding in findings})
    )
    controls.append({"kind": "node", "target": "hardcoded-colors", "checked": False})
    pull_request = int(environment["QG_PULL_REQUEST"])
    provenance: dict[str, object] = {
        "repository": environment["GITHUB_REPOSITORY"],
        "headSha": environment["QG_HEAD_SHA"],
        "workflowRunId": int(environment["GITHUB_RUN_ID"]),
        "runAttempt": int(environment["GITHUB_RUN_ATTEMPT"]),
        "graphDigest": graph_digest,
    }
    if pull_request:
        provenance["pullRequest"] = pull_request
    return {
        "schemaVersion": 0,
        "nodeId": "hardcoded-colors",
        "title": "Hardcoded color gate",
        "status": "failed" if findings else "passed",
        **({"failureKind": "quality"} if findings else {}),
        "summary": summary_body(findings),
        "metrics": [
            {"label": "Status", "value": "FAIL" if findings else "PASS"},
            {"label": "Findings", "value": str(len(findings))},
        ],
        "findings": [
            {
                "id": finding.finding_id,
                "severity": "error",
                "message": f"Hardcoded {finding.format} color: {finding.literal}",
                "ruleId": "hardcoded-color",
                "fingerprint": finding.finding_id,
                "location": location,
                "group": finding.format,
            }
            for finding, location in zip(findings, locations, strict=True)
        ],
        "annotations": [
            {
                "level": "error",
                "message": f"Hardcoded {finding.format} color: {finding.literal}",
                "title": "Hardcoded color gate",
                "location": location,
            }
            for finding, location in zip(findings, locations, strict=True)
        ],
        "diagnostics": [],
        "controls": controls,
        "notes": ["Color finding IDs are stable and location-sensitive."],
        "provenance": provenance,
    }


def main() -> int:
    """Scan the local diff and emit a native Quality Graph result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    arguments = parser.parse_args()
    changed_files = cast(
        "Callable[[str, tuple[str, ...]], tuple[ChangedFile, ...]]",
        importlib.import_module("qg_python.diff").changed_files,
    )
    findings = sorted(
        (
            finding
            for changed in changed_files(arguments.base, SOURCE_SUFFIXES)
            for finding in scan_file(changed.path, changed.source, set(changed.added_lines))
        ),
        key=lambda finding: (finding.path, finding.line, finding.column),
    )
    manifest = cast("dict[str, object]", json.loads(MANIFEST_PATH.read_text()))
    graph_digest = cast("str", manifest["graphDigest"])
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(result_value(findings, os.environ, graph_digest), indent=2, sort_keys=True)
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
