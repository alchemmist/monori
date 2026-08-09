"""Fail pull requests that add a new lint suppression."""

import os
import re
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast, override

from monori.ci.lib.annotations import AnnotationLevel, SourceAnnotation
from monori.ci.lib.findings import stable_finding_id
from monori.ci.lib.github import GitHub, RepositoryGitHubAPI
from monori.ci.quality_graph.base import ApprovalLifecycle, PullRequestSourceCheck
from monori.ci.quality_graph.models import CheckContext, CheckResult, Verdict
from monori.ci.quality_graph.reporting import (
    ReportFinding,
    ReportMetric,
    ReportModel,
    ReportStatus,
    admin_commands,
    finding_location,
    render_report,
)
from monori.common import (
    JsonValue,
    decode_json,
    integer_value,
    object_value,
    optional_string,
    string_value,
)

LABEL_PREFIX = "monori-suppress-"
SUPPRESSION_KEYS = r"(?:ignorePatterns|per-file-ignores|extend-ignore|disable_all|disabledRules)"
FINDING_ID_PREFIX = "suppression-"
STATUS_LABEL = "monori-suppression-failed"
APPROVAL_STATE_RE = re.compile(r"<!-- monori-suppression-approvals: ([0-9a-f,]*) -->")
PATCH_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
SOURCE_SUPPRESSION_RE = re.compile(
    r"(?:#\s*(?:noqa|type:\s*ignore|pyright:\s*ignore|pylint:\s*(?:disable|skip-file))"
    r"|#\s*pragma:\s*no cover"
    r"|//\s*(?:eslint-disable|@ts-(?:ignore|nocheck)|stryker\s+disable)"
    r"|/\*\s*(?:eslint-disable|stylelint-disable|@ts-(?:ignore|nocheck)|stryker\s+disable)"
    r")"
)
CONFIG_SUPPRESSION_RE = re.compile(
    rf"(?:\b{SUPPRESSION_KEYS}\b"
    r"|\b(?:noqa|ignore|ignores|exclude)\s*="
    r"|(?<!fetch-depth):\s*[\"']?(?:off|0)[\"']?(?:\s*[,}]|\s*$)"
    r"|\bzizmor\s*:\s*ignore\b|\bactionlint\s*:\s*ignore\b)"
)
TOML_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
TOML_KEY_RE = re.compile(
    r'^\s*((?:"[^"]+"|\'[^\']+\'|[A-Za-z0-9_-]+)'
    r'(?:\s*\.\s*(?:"[^"]+"|\'[^\']+\'|[A-Za-z0-9_-]+))*)\s*='
)
TOML_SUPPRESSION_SECTION_NAMES = {"per-file-ignores", "extend-per-file-ignores"}
APPROVALS = ApprovalLifecycle(
    "suppression",
    FINDING_ID_PREFIX,
    APPROVAL_STATE_RE,
    "<!-- monori-suppression-approvals: {ids} -->",
    legacy_label_prefix=LABEL_PREFIX,
    allow_file_commands=True,
)


@dataclass(frozen=True)
class Finding:
    """Represents one lint suppression finding."""

    path: str
    line: int
    column: int
    text: str
    finding_id: str


def display_finding_id(finding_id: str) -> str:
    """Format finding id for admin command output."""
    return f"{FINDING_ID_PREFIX}{finding_id}"


def added_lines_from_patch(patch: str) -> set[int]:
    """Extract added line numbers from a unified diff patch."""
    added: set[int] = set()
    new_line = 0
    for line in patch.splitlines():
        if line.startswith("@@"):
            match = PATCH_HUNK_RE.match(line)
            if not match:
                message = f"Cannot parse diff hunk: {line}"
                raise RuntimeError(message)
            new_line = int(match.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            added.add(new_line)
            new_line += 1
        elif (
            line.startswith("-") and not line.startswith("---")
        ) or line == r"\ No newline at end of file":
            continue
        elif new_line:
            new_line += 1
    return added


def _is_toml_suppression_section(section: str) -> bool:
    return section.rsplit(".", 1)[-1].strip('"').lower() in TOML_SUPPRESSION_SECTION_NAMES


def _directive_candidates(
    path: str, lines: list[str], added_lines: set[int], pattern: re.Pattern[str]
) -> list[tuple[int, int, str, str]]:
    candidates: list[tuple[int, int, str, str]] = []
    toml_section = ""
    is_toml = path.endswith(".toml")
    for line_number, line in enumerate(lines, 1):
        if is_toml:
            section_match = TOML_SECTION_RE.match(line)
            if section_match:
                toml_section = section_match.group(1)
        if line_number not in added_lines or _is_toml_suppression_section(toml_section):
            continue
        match = pattern.search(line)
        if match is None:
            continue
        code = f"{line[: match.start()]}{line[match.end() :]}"
        normalized_code = " ".join(code.split())
        normalized_directive = " ".join(match.group(0).lower().split())
        raw_id = f"{path}:{normalized_directive}:{normalized_code}"
        candidates.append((line_number, match.start(), line.strip(), raw_id))
    return candidates


def _toml_data(source: str, path: str) -> dict[str, JsonValue]:
    try:
        return cast("dict[str, JsonValue]", tomllib.loads(source))
    except tomllib.TOMLDecodeError as error:
        message = f"Cannot parse TOML file {path}: {error}"
        raise RuntimeError(message) from error


def _toml_section(data: dict[str, JsonValue], section: str) -> dict[str, JsonValue]:
    value: JsonValue = data
    for part in section.split("."):
        if not isinstance(value, dict):
            return {}
        value = value.get(part)
    return value if isinstance(value, dict) else {}


def _toml_suppression_sections(
    data: dict[str, JsonValue], prefix: tuple[str, ...] = ()
) -> list[str]:
    sections: list[str] = []
    for key, value in data.items():
        current = (*prefix, key)
        if isinstance(value, dict):
            if key.lower() in TOML_SUPPRESSION_SECTION_NAMES:
                sections.append(".".join(current))
            sections.extend(_toml_suppression_sections(value, current))
    return sections


def _contains_new_value(current: JsonValue, previous: JsonValue) -> bool:
    if isinstance(current, list) and isinstance(previous, list):
        return any(item not in previous for item in current)
    if isinstance(current, dict) and isinstance(previous, dict):
        return any(
            key not in previous or _contains_new_value(value, previous[key])
            for key, value in current.items()
        )
    return current != previous


def _toml_entry_spans(
    lines: list[str], added_lines: set[int]
) -> dict[tuple[str, str], tuple[int, int, int, str]]:
    spans: dict[tuple[str, str], tuple[int, int, int, str]] = {}
    section = ""
    line_number = 0
    while line_number < len(lines):
        line_number += 1
        line = lines[line_number - 1]
        section_match = TOML_SECTION_RE.match(line)
        if section_match:
            section = section_match.group(1)
            continue
        match = TOML_KEY_RE.match(line)
        if not _is_toml_suppression_section(section) or match is None:
            continue
        start = line_number
        end = start
        bracket_depth = line.count("[") - line.count("]")
        while bracket_depth > 0 and end < len(lines):
            end += 1
            continuation = lines[end - 1]
            bracket_depth += continuation.count("[") - continuation.count("]")
        if any(number in added_lines for number in range(start, end + 1)):
            key_text = match.group(1)
            key_data = _toml_data(f"{key_text} = 0\n", "TOML key")
            if len(key_data) != 1:
                message = f"Cannot identify TOML suppression key on line {start}"
                raise RuntimeError(message)
            key = next(iter(key_data))
            column = len(line) - len(line.lstrip())
            spans[(section, key)] = (start, end, column, line.strip())
        line_number = end
    return spans


def _toml_candidates(
    path: str,
    source: str,
    previous_source: str | None,
    added_lines: set[int],
) -> list[tuple[int, int, str, str]]:
    current = _toml_data(source, path)
    previous = _toml_data(previous_source, path) if previous_source is not None else {}
    candidates: list[tuple[int, int, str, str]] = []
    lines = source.splitlines()
    spans = _toml_entry_spans(lines, added_lines)
    for section in _toml_suppression_sections(current):
        current_section = _toml_section(current, section)
        previous_section = _toml_section(previous, section)
        for key, value in current_section.items():
            old_value = previous_section.get(key)
            if key not in previous_section or _contains_new_value(value, old_value):
                span = spans.get((section, key))
                if span is None:
                    message = f"Cannot locate changed TOML suppression key {key!r} in {path}"
                    raise RuntimeError(message)
                start, _, column, text = span
                entry = " ".join(" ".join(lines[start - 1 : span[1]]).split())
                raw_id = f"{path}:toml-section:{section}:{entry}"
                candidates.append((start, column, text, raw_id))
    return candidates


def scan_file(
    path: str,
    source: str,
    added_lines: set[int],
    previous_source: str | None = None,
) -> list[Finding]:
    """Scan changed lines in a file and emit suppression findings."""
    is_config = path.endswith((".toml", ".json", ".jsonc", ".yaml", ".yml")) or any(
        name in path.lower() for name in ("eslint.config", "stylelint", "knip.config")
    )
    lines = source.splitlines()
    pattern = CONFIG_SUPPRESSION_RE if is_config else SOURCE_SUPPRESSION_RE
    candidates = _directive_candidates(path, lines, added_lines, pattern)
    if path.endswith(".toml"):
        candidates.extend(_toml_candidates(path, source, previous_source, added_lines))
    duplicates = Counter(raw_id for _, _, _, raw_id in candidates)
    findings: list[Finding] = []
    for line_number, column, text, raw_id in candidates:
        disambiguator = f":{line_number}" if duplicates[raw_id] > 1 else ""
        finding_id = stable_finding_id(raw_id, disambiguator)
        findings.append(Finding(path, line_number, column, text, finding_id))
    return findings


class SuppressionCheck(PullRequestSourceCheck[Finding]):
    """Find newly added lint-rule suppressions in changed files."""

    gate = "suppression"
    job_id = "suppressions"
    report_marker = "suppression"
    approval_lifecycle = APPROVALS
    supports_ignore_file = True
    failure_label: ClassVar[str | None] = STATUS_LABEL

    @override
    def collect(self, context: CheckContext) -> CheckResult[Finding]:
        findings = tuple(
            finding
            for path, source in context.files.items()
            for finding in scan_file(
                path,
                source,
                set(context.changed_lines.get(path, frozenset())),
                context.previous_files.get(path),
            )
        )
        verdict = Verdict.FAIL if findings else Verdict.PASS
        return CheckResult(findings, verdict)

    @override
    def collect_pull_request(
        self, github: RepositoryGitHubAPI, pull: dict[str, JsonValue]
    ) -> list[Finding]:
        """Collect newly introduced suppressions from the pull request."""
        return changed_files(github, pull)

    @override
    def render_summary(
        self, findings: list[Finding], approved: set[str], pull_request_url: str
    ) -> str:
        """Render the lint-suppression report."""
        return summary_body(findings, approved, pull_request_url)

    @override
    def source_annotation(self, finding: Finding) -> SourceAnnotation:
        """Build an error annotation for a new lint suppression."""
        return SourceAnnotation(
            finding.path,
            finding.line,
            finding.line,
            f"New lint suppression: {finding.text}",
            AnnotationLevel.FAILURE,
            start_column=finding.column + 1,
            end_column=finding.column + 1,
        )


def changed_files(github: RepositoryGitHubAPI, pull: dict[str, JsonValue]) -> list[Finding]:
    """Collect suppression findings from files changed in a pull request."""
    number = integer_value(pull["number"], "pull request number")
    head = object_value(pull["head"], "head")
    head_sha = string_value(head["sha"], "head sha")
    base = pull.get("base")
    base_sha = None
    if base is not None:
        base_sha = string_value(object_value(base, "base")["sha"], "base sha")
    files: dict[str, str] = {}
    previous_files: dict[str, str] = {}
    changed_lines: dict[str, frozenset[int]] = {}
    for file in github.paged(f"/pulls/{number}/files"):
        path = string_value(file["filename"], "changed filename")
        if file.get("status") == "removed" or not path.endswith(
            (
                ".py",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".mjs",
                ".cjs",
                ".css",
                ".scss",
                ".sass",
                ".vue",
                ".toml",
                ".json",
                ".jsonc",
                ".yaml",
                ".yml",
            )
        ):
            continue
        source = github.file_text(path, head_sha)
        patch = optional_string(file.get("patch"))
        if source is None or not patch:
            continue
        files[path] = source
        if base_sha is not None:
            previous_source = github.file_text(path, base_sha)
            if previous_source is not None:
                previous_files[path] = previous_source
        changed_lines[path] = frozenset(added_lines_from_patch(patch))
    result = SuppressionCheck().collect(CheckContext(files, changed_lines, previous_files))
    return sorted(result.findings, key=lambda finding: (finding.path, finding.line, finding.column))


def summary_body(findings: list[Finding], approved: set[str], pr_url: str) -> str:
    """Build the suppressions check summary block for workflow output."""
    active = [finding for finding in findings if finding.finding_id not in approved]
    return render_report(
        ReportModel(
            "suppression",
            ReportStatus.PASSED if not active else ReportStatus.FAILED,
            metrics=(
                ReportMetric("Status", "PASS" if not active else "FAIL"),
                ReportMetric("Findings", str(len(findings))),
                ReportMetric("Active", str(len(active))),
                ReportMetric("Approved", str(len(findings) - len(active))),
            ),
            findings=tuple(
                ReportFinding(
                    f"`{finding.text.replace('`', '\\`')[:200]}` · "
                    f"`{display_finding_id(finding.finding_id)}`",
                    approved=finding.finding_id in approved,
                    location=finding_location(pr_url, finding.path, finding.line),
                )
                for finding in findings
            ),
            admin=admin_commands(
                "suppression",
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
                (
                    "Finding IDs, gate names, and file paths may be comma-separated.",
                    "Approvals persist while the finding fingerprint stays unchanged.",
                ),
            ),
        )
    )


def main() -> int:
    """Run suppression gate and return non-zero exit code on active findings."""
    github = GitHub()
    event = object_value(decode_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()), "event")
    return SuppressionCheck().run_pull_request_gate(github, event)


if __name__ == "__main__":
    raise SystemExit(main())
