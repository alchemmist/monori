"""Fail pull requests that add hardcoded web colors."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, ClassVar, override

from monori.ci.lib.annotations import AnnotationLevel, SourceAnnotation
from monori.ci.lib.findings import stable_finding_id
from monori.ci.quality_graph.base import (
    ApprovalLifecycle,
    PullRequestSourceCheck,
    QualityRuntime,
    read_github_event,
)
from monori.ci.quality_graph.checks.suppressions import added_lines_from_patch
from monori.ci.quality_graph.models import CheckContext, CheckResult, Metric, Verdict
from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.reporting import (
    RenderedCheckReport,
    ReportModel,
    ReportStatus,
    admin_commands,
    render_report,
)
from monori.common import JsonValue, integer_value, object_value, optional_string, string_value

if TYPE_CHECKING:
    from monori.ci.lib.github import RepositoryGitHubAPI

FINDING_ID_PREFIX = "color-"
STATUS_LABEL = "monori-hardcoded-color-failed"
APPROVAL_STATE_RE = re.compile(r"<!-- monori-color-approvals: ([0-9a-f,]*) -->")
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
APPROVALS = ApprovalLifecycle(
    "color",
    FINDING_ID_PREFIX,
    APPROVAL_STATE_RE,
    "<!-- monori-color-approvals: {ids} -->",
    allow_file_commands=True,
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


def display_finding_id(finding_id: str) -> str:
    """Format a finding ID for administrator commands."""
    return f"{FINDING_ID_PREFIX}{finding_id}"


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
                    stable_finding_id(raw_id),
                )
            )
    return findings


class HardcodedColorCheck(PullRequestSourceCheck[Finding]):
    """Find hardcoded web colors on added pull-request lines."""

    definition = WORKFLOW_JOB_BY_ID["hardcoded-colors"]
    approval_lifecycle = APPROVALS
    supports_ignore_file = True
    failure_label: ClassVar[str | None] = STATUS_LABEL

    @override
    def collect(self, context: CheckContext) -> CheckResult[Finding]:
        findings = tuple(
            finding
            for path, source in context.files.items()
            for finding in scan_file(path, source, set(context.changed_lines.get(path, ())))
        )
        return CheckResult(findings, Verdict.FAIL if findings else Verdict.PASS)

    @override
    def collect_pull_request(
        self, github: RepositoryGitHubAPI, pull: dict[str, JsonValue]
    ) -> list[Finding]:
        """Collect newly introduced colors from the pull request."""
        return changed_files(github, pull)

    @override
    def render_summary(
        self, findings: list[Finding], approved: set[str], pull_request_url: str
    ) -> RenderedCheckReport:
        """Render the hardcoded-color report."""
        return summary_body(findings, approved)

    @override
    def source_annotation(self, finding: Finding) -> SourceAnnotation:
        """Build an exact error annotation for a color literal."""
        return SourceAnnotation(
            finding.path,
            finding.line,
            finding.line,
            f"Hardcoded {finding.format} color: {finding.literal}",
            AnnotationLevel.FAILURE,
            start_column=finding.column + 1,
            end_column=finding.column + len(finding.literal),
        )


def changed_files(github: RepositoryGitHubAPI, pull: dict[str, JsonValue]) -> list[Finding]:
    """Collect color findings from supported changed files in a pull request."""
    number = integer_value(pull["number"], "pull request number")
    head_sha = string_value(object_value(pull["head"], "head")["sha"], "head sha")
    findings: list[Finding] = []
    for file in github.paged(f"/pulls/{number}/files"):
        path = string_value(file["filename"], "changed filename")
        patch = optional_string(file.get("patch"))
        if file.get("status") == "removed" or not patch or not should_scan(path):
            continue
        source = github.file_text(path, head_sha)
        if source is not None:
            findings.extend(scan_file(path, source, added_lines_from_patch(patch)))
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.column))


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("`", "\\`").replace("\n", " ")


def summary_body(findings: list[Finding], approved: set[str]) -> RenderedCheckReport:
    """Build the hardcoded-color Job Summary."""
    active = [finding for finding in findings if finding.finding_id not in approved]
    rows = [
        "| File | Line | Literal | Format | Context | Status |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| `{_cell(finding.path)}` | {finding.line} | `{_cell(finding.literal)}` | "
        f"{finding.format} | `{_cell(finding.context[:200])}` | "
        f"{'approved' if finding.finding_id in approved else 'active'} |"
        for finding in findings
    )
    return render_report(
        ReportModel(
            "hardcoded-colors",
            ReportStatus.PASSED if not active else ReportStatus.FAILED,
            metrics=(
                Metric("Status", "PASS" if not active else "FAIL"),
                Metric("Findings", str(len(findings))),
                Metric("Active", str(len(active))),
                Metric("Approved", str(len(findings) - len(active))),
            ),
            content="\n".join(rows) if findings else "No hardcoded colors found.",
            admin=admin_commands(
                "color",
                [display_finding_id(finding.finding_id) for finding in active],
                [
                    display_finding_id(finding.finding_id)
                    for finding in findings
                    if finding.finding_id in approved
                ],
                {
                    path: [
                        display_finding_id(finding.finding_id)
                        for finding in active
                        if finding.path == path
                    ]
                    for path in {finding.path for finding in active}
                },
            ),
        )
    )


def main() -> int:
    """Run the hardcoded-color gate."""
    runtime = QualityRuntime.from_environment()
    return HardcodedColorCheck().run_pull_request_gate(
        runtime.github,
        read_github_event(),
        runtime.publisher,
        read_only=runtime.read_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
