"""Fail pull requests that add a new lint suppression."""

import base64
import hashlib
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Protocol, cast, override

import httpx

from ci.lib.comments import upsert_comment
from ci.lib.github import (
    GITHUB_PAGE_SIZE,
    HTTP_NO_CONTENT,
    HTTP_NOT_FOUND,
    REQUEST_TIMEOUT_SECONDS,
)
from ci.quality_graph.base import QualityCheck
from ci.quality_graph.commands import (
    QualityGraphCommand,
    admin_command_lines,
    command_targets_gate,
    parse_command,
    validate_command,
)
from ci.quality_graph.models import CheckContext, CheckResult, Verdict

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

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
TOML_SUPPRESSION_SECTION_NAMES = {"per-file-ignores", "extend-per-file-ignores"}
WORKFLOW_RUNS_PER_PAGE = GITHUB_PAGE_SIZE


def json_object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    """Parse value as JSON object or raise a type error."""
    if not isinstance(value, dict):
        message = f"Expected a JSON object for {context}"
        raise TypeError(message)
    return value


def json_array(value: JsonValue, context: str) -> list[JsonValue]:
    """Parse value as JSON array or raise a type error."""
    if not isinstance(value, list):
        message = f"Expected a JSON array for {context}"
        raise TypeError(message)
    return value


def json_string(value: JsonValue, context: str) -> str:
    """Parse value as JSON string or raise a type error."""
    if not isinstance(value, str):
        message = f"Expected a JSON string for {context}"
        raise TypeError(message)
    return value


def json_integer(value: JsonValue, context: str) -> int:
    """Parse value as JSON integer or raise a type error."""
    if isinstance(value, bool) or not isinstance(value, int):
        message = f"Expected a JSON integer for {context}"
        raise TypeError(message)
    return value


def optional_string(value: JsonValue) -> str | None:
    """Return a string value or None."""
    return value if isinstance(value, str) else None


def decode_json(data: bytes | str) -> JsonValue:
    """Decode JSON payload to Python object."""
    return cast("JsonValue", json.loads(data))


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
            items = json_array(
                self.request(
                    "GET", f"{path}{separator}per_page={WORKFLOW_RUNS_PER_PAGE}&page={page}"
                ),
                path,
            )
            result.extend(json_object(item, path) for item in items)
            if len(items) < WORKFLOW_RUNS_PER_PAGE:
                return result
            page += 1

    def file_text(self, path: str, ref: str) -> str | None:
        """Load file content at ref from GitHub API, returning None when missing."""
        encoded = urllib.parse.quote(path, safe="")
        response = self.request("GET", f"/contents/{encoded}?ref={urllib.parse.quote(ref)}")
        if response is None:
            return None
        data = json_object(response, path)
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


class GitHubAPI(Protocol):
    """Protocol for the GitHub API client used by suppression checks."""

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Make a GitHub API request and return decoded JSON or None."""
        ...

    def paged(self, path: str) -> list[dict[str, JsonValue]]:
        """Request and return all paginated GitHub objects for an endpoint."""
        ...

    def file_text(self, path: str, ref: str) -> str | None:
        """Load file contents from repository at a given ref."""
        ...

    def ensure_label(self, name: str) -> None:
        """Ensure a label exists for the current repository."""
        ...


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


def scan_file(path: str, source: str, added_lines: set[int]) -> list[Finding]:
    """Scan changed lines in a file and emit suppression findings."""
    candidates: list[tuple[int, int, str, str]] = []
    is_toml = path.endswith(".toml")
    is_config = path.endswith((".toml", ".json", ".jsonc", ".yaml", ".yml")) or any(
        name in path.lower() for name in ("eslint.config", "stylelint", "knip.config")
    )
    pattern = CONFIG_SUPPRESSION_RE if is_config else SOURCE_SUPPRESSION_RE
    toml_section = ""
    for line_number, line in enumerate(source.splitlines(), 1):
        if is_toml:
            section_match = TOML_SECTION_RE.match(line)
            if section_match:
                toml_section = section_match.group(1)
        if line_number not in added_lines:
            continue
        match = pattern.search(line)
        if match is not None:
            code = f"{line[: match.start()]}{line[match.end() :]}"
            normalized_code = " ".join(code.split())
            normalized_directive = " ".join(match.group(0).lower().split())
            column = match.start()
        elif (
            is_toml
            and toml_section.rsplit(".", 1)[-1].strip('"').lower() in TOML_SUPPRESSION_SECTION_NAMES
            and line.strip()
            and not line.lstrip().startswith("#")
        ):
            normalized_code = " ".join(line.split())
            normalized_directive = f"toml-section:{toml_section.lower()}"
            column = len(line) - len(line.lstrip())
        else:
            continue
        raw_id = f"{path}:{normalized_directive}:{normalized_code}"
        candidates.append((line_number, column, line.strip(), raw_id))
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

    @override
    def collect(self, context: CheckContext) -> CheckResult[Finding]:
        findings = tuple(
            finding
            for path, source in context.files.items()
            for finding in scan_file(
                path,
                source,
                set(context.changed_lines.get(path, frozenset())),
            )
        )
        verdict = Verdict.FAIL if findings else Verdict.PASS
        return CheckResult(findings, verdict)


def approval_state(body: str) -> set[str]:
    """Extract approved finding ids from the suppression approvals marker."""
    match = APPROVAL_STATE_RE.search(body)
    return set(match.group(1).split(",")) if match and match.group(1) else set()


def update_approval_state(
    github: GitHubAPI, number: int, pull: dict[str, JsonValue], approved: set[str]
) -> None:
    """Update PR body marker that tracks active suppression approvals."""
    body = optional_string(pull.get("body")) or ""
    marker = f"<!-- monori-suppression-approvals: {','.join(sorted(approved))} -->"
    updated_body = APPROVAL_STATE_RE.sub(marker, body)
    if updated_body == body:
        updated_body = f"{body.rstrip()}\n\n{marker}" if body.strip() else marker
    if updated_body != body:
        github.request("PATCH", f"/pulls/{number}", {"body": updated_body})


def changed_files(github: GitHubAPI, pull: dict[str, JsonValue]) -> list[Finding]:
    """Collect suppression findings from files changed in a pull request."""
    number = json_integer(pull["number"], "pull request number")
    head = json_object(pull["head"], "head")
    head_sha = json_string(head["sha"], "head sha")
    files: dict[str, str] = {}
    changed_lines: dict[str, frozenset[int]] = {}
    for file in github.paged(f"/pulls/{number}/files"):
        path = json_string(file["filename"], "changed filename")
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
        changed_lines[path] = frozenset(added_lines_from_patch(patch))
    result = SuppressionCheck().collect(CheckContext(files, changed_lines))
    return sorted(result.findings, key=lambda finding: (finding.path, finding.line, finding.column))


def is_admin(github: GitHubAPI, login: str) -> bool:
    """Return True when login corresponds to repository admin."""
    encoded = urllib.parse.quote(login, safe="")
    permission = github.request("GET", f"/collaborators/{encoded}/permission")
    return (
        permission is not None
        and json_object(permission, "permission").get("permission") == "admin"
    )


def sync_approvals(
    github: GitHubAPI,
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


def sync_status_label(github: GitHubAPI, number: int, *, has_active_findings: bool) -> None:
    """Create or remove suppression-failed status label based on current findings."""
    if has_active_findings:
        github.ensure_label(STATUS_LABEL)
        github.request("POST", f"/issues/{number}/labels", {"labels": [STATUS_LABEL]})
    else:
        github.request(
            "DELETE",
            f"/issues/{number}/labels/{urllib.parse.quote(STATUS_LABEL, safe='')}",
        )


def finding_url(pr_url: str, finding: Finding) -> str:
    """Build a URL for a suppression finding in the pull request diff."""
    diff_hash = hashlib.sha256(finding.path.encode()).hexdigest()
    return f"{pr_url}/changes#diff-{diff_hash}R{finding.line}"


def summary_body(findings: list[Finding], approved: set[str], pr_url: str) -> str:
    """Build the suppressions check summary block for workflow output."""
    active = [finding for finding in findings if finding.finding_id not in approved]
    status = "✅ PASS" if not active else "❌ FAIL"
    lines = [
        "## Lint suppression gate",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Status | {status} |",
        f"| Findings | {len(findings)} |",
        f"| Active | {len(active)} |",
        f"| Approved | {len(findings) - len(active)} |",
        "",
        f"<details><summary>Findings ({len(findings)})</summary>",
        "",
    ]
    for finding in findings:
        marker = "✔" if finding.finding_id in approved else "✗"
        text = finding.text.replace("`", "\\`")[:200]
        location = f"{finding.path}:{finding.line}"
        lines.append(
            f"- {marker} [`{location}`]({finding_url(pr_url, finding)}) — `{text}` · "
            f"`{display_finding_id(finding.finding_id)}`"
        )
    lines.extend(
        [
            "",
            "</details>",
            "",
            "<details><summary>For repository administrators</summary>",
            "",
            *admin_command_lines(
                "suppression",
                [display_finding_id(finding.finding_id) for finding in active],
                [
                    display_finding_id(finding.finding_id)
                    for finding in findings
                    if finding.finding_id in approved
                ],
                [finding.path for finding in active],
            ),
            "",
            "Finding IDs, gate names, and file paths may be comma-separated.",
            "Approvals persist while the finding fingerprint stays unchanged.",
            "</details>",
        ]
    )
    return "\n".join(lines)


def rerun_gate(github: GitHubAPI, number: int) -> None:
    """Rerun the latest workflow run that belongs to the pull request."""
    matching: list[dict[str, JsonValue]] = []
    for page in count(1):
        runs = json_object(
            github.request(
                "GET",
                "/actions/workflows/pr-checks.yaml/runs"
                f"?event=pull_request&per_page={WORKFLOW_RUNS_PER_PAGE}&page={page}",
            ),
            "workflow runs",
        )
        page_runs = json_array(runs.get("workflow_runs", []), "workflow runs")
        for run in page_runs:
            run_data = json_object(run, "workflow run")
            if any(
                json_object(pull, "workflow pull request").get("number") == number
                for pull in json_array(run_data.get("pull_requests", []), "workflow pull requests")
            ):
                matching.append(run_data)
        if len(page_runs) < WORKFLOW_RUNS_PER_PAGE or matching:
            break
    if matching:
        latest = max(matching, key=lambda run: optional_string(run.get("created_at")) or "")
        run_id = json_integer(latest["id"], "workflow run id")
        github.request("POST", f"/actions/runs/{run_id}/rerun-failed-jobs")


def main() -> int:
    """Run suppression gate and return non-zero exit code on active findings."""
    github = GitHub()
    event = json_object(decode_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()), "event")
    pull_event = json_object(event.get("pull_request", {}), "pull request event")
    issue = json_object(event.get("issue", {}), "issue event")
    number_value = pull_event.get("number") or issue.get("number")
    if not isinstance(number_value, int) or not (pull_event or issue.get("pull_request")):
        return 0
    number = number_value
    pull = json_object(github.request("GET", f"/pulls/{number}"), "pull request")
    findings = changed_files(github, pull)
    comment = json_object(event.get("comment", {}), "comment")
    command = parse_command((optional_string(comment.get("body")) or "").strip())
    if command and validate_command(command) is not None:
        command = None
    if command and not command_targets_gate(command, "suppression"):
        command = None
    author_data = json_object(comment.get("user", {}), "comment user")
    author = optional_string(author_data.get("login")) if command else None
    approved, admin = sync_approvals(
        github, number, pull, findings, SyncApprovalCommandState(command, author)
    )
    active = [finding for finding in findings if finding.finding_id not in approved]
    sync_status_label(github, number, has_active_findings=bool(active))
    pr_url = json_string(pull["html_url"], "pull request URL")
    upsert_comment(github, number, "suppression", summary_body(findings, approved, pr_url))
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
