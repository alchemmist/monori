"""Fail pull requests that add a new lint suppression."""

import base64
import hashlib
import json
import os
import re
import sys
import tomllib
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import cast, override

import httpx

from monori.ci.lib.github import (
    GITHUB_PAGE_SIZE,
    HTTP_NO_CONTENT,
    HTTP_NOT_FOUND,
    REQUEST_TIMEOUT_SECONDS,
    RepositoryGitHubAPI,
)
from monori.ci.quality_graph.base import QualityCheck
from monori.ci.quality_graph.commands import (
    QualityGraphCommand,
    command_targets_gate,
    parse_command,
    validate_command,
)
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
    array_value,
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
WORKFLOW_RUNS_PER_PAGE = GITHUB_PAGE_SIZE


@dataclass(frozen=True)
class Finding:
    """Represents one lint suppression finding."""

    path: str
    line: int
    column: int
    text: str
    finding_id: str


@dataclass(frozen=True)
class SyncApprovalCommandState:
    """Input state for approval-sync requests."""

    command: QualityGraphCommand | None
    author: str | None


def display_finding_id(finding_id: str) -> str:
    """Format finding id for admin command output."""
    return f"{FINDING_ID_PREFIX}{finding_id}"


class GitHub:
    """Thin GitHub API client used by suppression checks."""

    def __init__(self) -> None:
        """Read required GitHub API configuration from environment."""
        self.base_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repository = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Execute one GitHub request and return decoded JSON."""
        url = f"{self.base_url}/repos/{self.repository}{path}"
        data = None if payload is None else json.dumps(payload).encode()
        try:
            response = httpx.request(
                method,
                url,
                content=data,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "Content-Type": "application/json",
                },
            )
        except httpx.RequestError as error:
            message = f"GitHub API {method} {path} failed: {error}"
            raise RuntimeError(message) from error
        if response.status_code == HTTP_NO_CONTENT:
            return None
        if response.status_code == HTTP_NOT_FOUND and method in {"GET", "DELETE"}:
            return None
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            message = f"GitHub API {method} {path} failed: HTTP {response.status_code}"
            raise RuntimeError(message) from error
        return cast("JsonValue", response.json())

    def paged(self, path: str) -> list[dict[str, JsonValue]]:
        """Retrieve all pages for a GitHub list endpoint."""
        result: list[dict[str, JsonValue]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            items = array_value(
                self.request(
                    "GET", f"{path}{separator}per_page={WORKFLOW_RUNS_PER_PAGE}&page={page}"
                ),
                path,
            )
            result.extend(object_value(item, path) for item in items)
            if len(items) < WORKFLOW_RUNS_PER_PAGE:
                return result
            page += 1

    def file_text(self, path: str, ref: str) -> str | None:
        """Load file content at ref from GitHub API, returning None when missing."""
        encoded = urllib.parse.quote(path, safe="")
        response = self.request("GET", f"/contents/{encoded}?ref={urllib.parse.quote(ref)}")
        if response is None:
            return None
        data = object_value(response, path)
        content = optional_string(data.get("content"))
        if content:
            return base64.b64decode(content).decode("utf-8")
        download_url = optional_string(data.get("download_url"))
        if download_url:
            try:
                download_response = httpx.get(
                    download_url,
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                download_response.raise_for_status()
            except httpx.HTTPError as error:
                message = f"Cannot read {path} at {ref}: {error}"
                raise RuntimeError(message) from error
            return download_response.text
        return None

    def ensure_label(self, name: str) -> None:
        """Ensure a repository label exists, creating it when missing."""
        encoded = urllib.parse.quote(name, safe="")
        if self.request("GET", f"/labels/{encoded}") is None:
            self.request(
                "POST",
                "/labels",
                {
                    "name": name,
                    "color": "b60205",
                    "description": "Approved lint suppression",
                },
            )


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
        finding_id = hashlib.sha256(f"{raw_id}{disambiguator}".encode()).hexdigest()[:12]
        findings.append(Finding(path, line_number, column, text, finding_id))
    return findings


class SuppressionCheck(QualityCheck[Finding]):
    """Find newly added lint-rule suppressions in changed files."""

    gate = "suppression"
    report_marker = "suppression"

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


def approval_state(body: str) -> set[str]:
    """Extract approved finding ids from the suppression approvals marker."""
    match = APPROVAL_STATE_RE.search(body)
    return set(match.group(1).split(",")) if match and match.group(1) else set()


def update_approval_state(
    github: RepositoryGitHubAPI, number: int, pull: dict[str, JsonValue], approved: set[str]
) -> None:
    """Update PR body marker that tracks active suppression approvals."""
    body = optional_string(pull.get("body")) or ""
    marker = f"<!-- monori-suppression-approvals: {','.join(sorted(approved))} -->"
    updated_body = APPROVAL_STATE_RE.sub(marker, body)
    if updated_body == body:
        updated_body = f"{body.rstrip()}\n\n{marker}" if body.strip() else marker
    if updated_body != body:
        github.request("PATCH", f"/pulls/{number}", {"body": updated_body})


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


def is_admin(github: RepositoryGitHubAPI, login: str) -> bool:
    """Return True when login corresponds to repository admin."""
    encoded = urllib.parse.quote(login, safe="")
    permission = github.request("GET", f"/collaborators/{encoded}/permission")
    return (
        permission is not None
        and object_value(permission, "permission").get("permission") == "admin"
    )


def sync_approvals(
    github: RepositoryGitHubAPI,
    number: int,
    pull: dict[str, JsonValue],
    findings: list[Finding],
    command_state: SyncApprovalCommandState,
) -> tuple[set[str], bool]:
    """Update suppressions approval state and apply admin commands."""
    labels = github.paged(f"/issues/{number}/labels")
    finding_ids = {finding.finding_id for finding in findings}
    body = optional_string(pull.get("body")) or ""
    state_exists = APPROVAL_STATE_RE.search(body) is not None
    legacy_approved = {
        name[len(LABEL_PREFIX) :]
        for label in labels
        if (name := optional_string(label.get("name")))
        and name.startswith(LABEL_PREFIX)
        and name[len(LABEL_PREFIX) :] in finding_ids
    }
    for label in labels:
        name = optional_string(label.get("name"))
        if name and name.startswith(LABEL_PREFIX):
            github.request("DELETE", f"/issues/{number}/labels/{urllib.parse.quote(name, safe='')}")
    approved = (approval_state(body) if state_exists else legacy_approved) & finding_ids
    command = command_state.command
    author = command_state.author
    admin = command is not None and author is not None and is_admin(github, author)
    if not command or not admin:
        if not state_exists:
            update_approval_state(github, number, pull, approved)
        return approved, admin
    name = command.name
    arguments = command.arguments
    if name in {"help", "status"}:
        return approved, admin
    selected = {
        finding.finding_id
        for finding in findings
        if name == "ignore-file" and finding.path in arguments
    }
    if name in {"ignore", "remove-ignore"}:
        selected = (
            finding_ids
            if "suppression" in arguments
            else {
                argument[len(FINDING_ID_PREFIX) :]
                for argument in arguments
                if argument.startswith(FINDING_ID_PREFIX)
            }
        ) & finding_ids
    for finding_id in selected:
        if name == "remove-ignore":
            approved.discard(finding_id)
        else:
            approved.add(finding_id)
    update_approval_state(github, number, pull, approved)
    return approved, admin


def sync_status_label(
    github: RepositoryGitHubAPI, number: int, *, has_active_findings: bool
) -> None:
    """Create or remove suppression-failed status label based on current findings."""
    if has_active_findings:
        github.ensure_label(STATUS_LABEL)
        github.request("POST", f"/issues/{number}/labels", {"labels": [STATUS_LABEL]})
    else:
        github.request(
            "DELETE",
            f"/issues/{number}/labels/{urllib.parse.quote(STATUS_LABEL, safe='')}",
        )


def summary_body(findings: list[Finding], approved: set[str], pr_url: str) -> str:
    """Build the suppressions check summary block for workflow output."""
    active = [finding for finding in findings if finding.finding_id not in approved]
    return render_report(
        ReportModel(
            "suppression",
            ReportStatus.DONE if not active else ReportStatus.FAIL,
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
                [finding.path for finding in active],
                (
                    "Finding IDs, gate names, and file paths may be comma-separated.",
                    "Approvals persist while the finding fingerprint stays unchanged.",
                ),
            ),
        )
    )


def rerun_gate(github: RepositoryGitHubAPI, number: int) -> None:
    """Rerun the latest workflow run that belongs to the pull request."""
    matching: list[dict[str, JsonValue]] = []
    for page in count(1):
        runs = object_value(
            github.request(
                "GET",
                "/actions/workflows/pr-checks.yaml/runs"
                f"?event=pull_request&per_page={WORKFLOW_RUNS_PER_PAGE}&page={page}",
            ),
            "workflow runs",
        )
        page_runs = array_value(runs.get("workflow_runs", []), "workflow runs")
        for run in page_runs:
            run_data = object_value(run, "workflow run")
            if any(
                object_value(pull, "workflow pull request").get("number") == number
                for pull in array_value(run_data.get("pull_requests", []), "workflow pull requests")
            ):
                matching.append(run_data)
        if len(page_runs) < WORKFLOW_RUNS_PER_PAGE or matching:
            break
    if matching:
        latest = max(matching, key=lambda run: optional_string(run.get("created_at")) or "")
        run_id = integer_value(latest["id"], "workflow run id")
        github.request("POST", f"/actions/runs/{run_id}/rerun-failed-jobs")


def main() -> int:
    """Run suppression gate and return non-zero exit code on active findings."""
    github = GitHub()
    event = object_value(decode_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()), "event")
    pull_event = object_value(event.get("pull_request", {}), "pull request event")
    issue = object_value(event.get("issue", {}), "issue event")
    number_value = pull_event.get("number") or issue.get("number")
    if not isinstance(number_value, int) or not (pull_event or issue.get("pull_request")):
        return 0
    number = number_value
    report = SuppressionCheck().report(github, number)
    report.mark_in_progress()
    pull = object_value(github.request("GET", f"/pulls/{number}"), "pull request")
    findings = changed_files(github, pull)
    comment = object_value(event.get("comment", {}), "comment")
    command = parse_command((optional_string(comment.get("body")) or "").strip())
    if command and validate_command(command) is not None:
        command = None
    if command and not command_targets_gate(command, "suppression"):
        command = None
    author_data = object_value(comment.get("user", {}), "comment user")
    author = optional_string(author_data.get("login")) if command else None
    approved, admin = sync_approvals(
        github, number, pull, findings, SyncApprovalCommandState(command, author)
    )
    active = [finding for finding in findings if finding.finding_id not in approved]
    sync_status_label(github, number, has_active_findings=bool(active))
    pr_url = string_value(pull["html_url"], "pull request URL")
    report.publish(summary_body(findings, approved, pr_url))
    if admin:
        rerun_gate(github, number)
    for finding in findings:
        if finding.finding_id not in approved:
            sys.stderr.write(
                f"::error file={finding.path},line={finding.line},col={finding.column + 1}::"
                f"New lint suppression: {finding.text}\n"
            )
    return 1 if any(finding.finding_id not in approved for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
