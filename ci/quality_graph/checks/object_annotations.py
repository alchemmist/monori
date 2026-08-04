"""Check changed Python annotations for uses of the overly broad ``object`` type."""

import ast
import base64
import difflib
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
    HTTP_FORBIDDEN,
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

PATCH_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
IGNORE_LABEL_PREFIX = "monori-object-annotation-ignore-"
FINDING_ID_PREFIX = "object-"
FAILURE_LABEL = "monori-object-annotation-failed"
APPROVAL_STATE_RE = re.compile(r"<!-- monori-object-annotation-approvals: ([0-9a-f,]*) -->")
WORKFLOW_RUNS_PER_PAGE = GITHUB_PAGE_SIZE


def decode_json(data: bytes | str) -> JsonValue:
    """Decode raw JSON payload into typed JSON value."""
    return cast("JsonValue", json.loads(data))


def json_object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    """Parse value as JSON object for the given context."""
    if not isinstance(value, dict):
        message = f"Expected a JSON object for {context}"
        raise TypeError(message)
    return value


def json_array(value: JsonValue, context: str) -> list[JsonValue]:
    """Parse value as JSON array for the given context."""
    if not isinstance(value, list):
        message = f"Expected a JSON array for {context}"
        raise TypeError(message)
    return value


def json_string(value: JsonValue, context: str) -> str:
    """Parse value as JSON string for the given context."""
    if not isinstance(value, str):
        message = f"Expected a JSON string for {context}"
        raise TypeError(message)
    return value


def json_integer(value: JsonValue, context: str) -> int:
    """Parse value as JSON integer for the given context."""
    if isinstance(value, bool) or not isinstance(value, int):
        message = f"Expected a JSON integer for {context}"
        raise TypeError(message)
    return value


def optional_string(value: JsonValue) -> str | None:
    """Return a JSON string value or ``None``."""
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class Finding:
    """Object-type finding location and associated detection metadata."""

    path: str
    line: int
    column: int
    annotation: str
    finding_id: str


def display_finding_id(finding_id: str) -> str:
    """Return finding id prefixed for command addressing."""
    return f"{FINDING_ID_PREFIX}{finding_id}"


class GitHubAPIError(RuntimeError):
    """Raised when the GitHub API returns an unexpected non-retriable error."""

    def __init__(self, method: str, path: str, status: int) -> None:
        """Build a typed runtime error for GitHub HTTP failures."""
        super().__init__(f"GitHub API {method} {path} failed: HTTP {status}")
        self.status = status


class GitHub:
    """Small typed GitHub API client for annotation checks."""

    def __init__(self) -> None:
        """Initialize object-annotation gate GitHub client from environment."""
        self.base_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repository = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Send GitHub API request and return parsed JSON response."""
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
        if response.status_code == HTTP_FORBIDDEN and method in {"POST", "PATCH", "DELETE"}:
            return None
        if method in {"GET", "DELETE"} and response.status_code == HTTP_NOT_FOUND:
            return None
        if response.is_error:
            raise GitHubAPIError(method, path, response.status_code)
        return cast("JsonValue", response.json())

    def paged(self, path: str) -> list[dict[str, JsonValue]]:
        """Read all pages from a GitHub list endpoint."""
        result: list[dict[str, JsonValue]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            response = self.request(
                "GET",
                f"{path}{separator}per_page={WORKFLOW_RUNS_PER_PAGE}&page={page}",
            )
            items = json_array(response, path)
            result.extend(json_object(item, path) for item in items)
            if len(items) < WORKFLOW_RUNS_PER_PAGE:
                return result
            page += 1

    def file_text(self, path: str, ref: str) -> str | None:
        """Read file content from repository at the given git reference."""
        encoded = urllib.parse.quote(path, safe="")
        raw_response = self.request("GET", f"/contents/{encoded}?ref={urllib.parse.quote(ref)}")
        if raw_response is None:
            return None
        response = json_object(raw_response, path)
        if response.get("encoding") == "base64" and response.get("content"):
            content = json_string(response["content"], f"{path}.content")
            return base64.b64decode(content).decode("utf-8")
        download_url = optional_string(response.get("download_url"))
        if not download_url:
            message = f"Cannot read {path} at {ref}"
            raise RuntimeError(message)
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

    def ensure_label(self, name: str) -> None:
        """Ensure repository has a label; create it if missing."""
        encoded = urllib.parse.quote(name, safe="")
        if self.request("GET", f"/labels/{encoded}") is None:
            self.request(
                "POST",
                "/labels",
                {
                    "name": name,
                    "color": "b60205",
                    "description": "Object annotation gate state",
                },
            )


class GitHubAPI(Protocol):
    """Public interface required by object-annotation checks for GitHub calls."""

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Execute request to GitHub API endpoint."""
        ...

    def paged(self, path: str) -> list[dict[str, JsonValue]]:
        """Read all pages from a list-like GitHub endpoint."""
        ...

    def file_text(self, path: str, ref: str) -> str | None:
        """Return file text from repository at a specific reference."""
        ...

    def ensure_label(self, name: str) -> None:
        """Ensure the repository label exists."""
        ...


def changed_lines(before: str | None, after: str) -> set[int]:
    """Compute changed line numbers between two text snapshots."""
    before_lines = [] if before is None else before.splitlines()
    after_lines = after.splitlines()
    changed: set[int] = set()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines, autojunk=False)
    for tag, _, _, new_start, new_end in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            changed.update(range(new_start + 1, new_end + 1))
    return changed


def added_lines_from_patch(patch: str) -> set[int]:
    """Parse unified diff patch and return added line numbers."""
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
        elif line.startswith("-") and not line.startswith("---"):
            continue
        elif new_line:
            new_line += 1
    return added


def annotation_nodes(tree: ast.AST) -> list[ast.expr]:
    """Collect annotation nodes that can contain ``object`` references."""
    nodes: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            arguments.extend(
                argument for argument in (node.args.vararg, node.args.kwarg) if argument
            )
            nodes.extend(argument.annotation for argument in arguments if argument.annotation)
            if node.returns:
                nodes.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            nodes.append(node.annotation)
    return nodes


def contains_object(annotation: ast.expr) -> tuple[int, int] | None:
    """Check annotation expression for a direct or nested ``object`` annotation."""
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name) and node.id == "object":
            return node.lineno, node.col_offset
        if isinstance(node, ast.Attribute) and node.attr == "object":
            return node.lineno, node.col_offset
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                parsed = ast.parse(node.value, mode="eval")
            except SyntaxError:
                continue
            if contains_object(parsed.body):
                return node.lineno, node.col_offset
    return None


def scan_file(path: str, source: str, changed: set[int]) -> list[Finding]:
    """Scan a Python file and return object-typed annotations on changed lines."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        sys.stderr.write(
            f"::error file={path},line={error.lineno or 1}::Cannot parse Python file: {error}\n"
        )
        return []

    candidates: list[tuple[int, int, str, str]] = []
    for annotation in annotation_nodes(tree):
        object_location = contains_object(annotation)
        if object_location is None or object_location[0] not in changed:
            continue
        object_line, object_column = object_location
        rendered = ast.unparse(annotation)
        raw_id = f"{path}:{' '.join(rendered.split())}"
        candidates.append((object_line, object_column, rendered, raw_id))
    duplicates = Counter(raw_id for _, _, _, raw_id in candidates)
    findings: list[Finding] = []
    for object_line, object_column, rendered, raw_id in candidates:
        disambiguator = f":{object_line}:{object_column}" if duplicates[raw_id] > 1 else ""
        finding_id = hashlib.sha256(f"{raw_id}{disambiguator}".encode()).hexdigest()[:12]
        findings.append(Finding(path, object_line, object_column, rendered, finding_id))
    return sorted(findings, key=lambda finding: (finding.line, finding.column, finding.annotation))


class ObjectAnnotationCheck(QualityCheck[Finding]):
    """Find changed annotations that use the overly broad ``object`` type."""

    gate = "object"

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


def finding_url(pr_url: str, finding: Finding) -> str:
    """Build URL for a finding line in the pull request diff."""
    diff_hash = hashlib.sha256(finding.path.encode()).hexdigest()
    return f"{pr_url}/changes#diff-{diff_hash}R{finding.line}"


def summary_body(findings: list[Finding], approved: set[str], pr_url: str) -> str:
    """Render the summary markdown shown for object annotation check."""
    active = [finding for finding in findings if finding.finding_id not in approved]
    status = "✅ PASS" if not active else "❌ FAIL"
    lines = [
        "## Python object annotation gate",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Status | {status} |",
        f"| Findings | {len(findings)} |",
        f"| Active | {len(active)} |",
        f"| Approved | {len(findings) - len(active)} |",
        "",
        f"<details><summary>List of problems ({len(findings)})</summary>",
        "",
    ]
    for finding in findings:
        marker = "✔" if finding.finding_id in approved else "✗"
        location = f"{finding.path}:{finding.line}"
        lines.append(
            f"- {marker} [`{location}`]({finding_url(pr_url, finding)}) "
            f"— `{finding.annotation}` · `{display_finding_id(finding.finding_id)}`"
        )
    lines.extend(
        [
            "",
            "</details>",
            "",
            "<details><summary>For repository administrators</summary>",
            "",
            *admin_command_lines(
                "object",
                [display_finding_id(finding.finding_id) for finding in active],
                [
                    display_finding_id(finding.finding_id)
                    for finding in findings
                    if finding.finding_id in approved
                ],
                [finding.path for finding in active],
            ),
            "</details>",
        ]
    )
    return "\n".join(lines)


def approval_state(body: str) -> set[str]:
    """Extract currently approved finding ids from PR body marker."""
    match = APPROVAL_STATE_RE.search(body)
    return set(match.group(1).split(",")) if match and match.group(1) else set()


def update_approval_state(
    github: GitHubAPI, number: int, pull: dict[str, JsonValue], approved: set[str]
) -> None:
    """Update PR body marker with currently approved finding ids."""
    body = optional_string(pull.get("body")) or ""
    marker = f"<!-- monori-object-annotation-approvals: {','.join(sorted(approved))} -->"
    updated_body = APPROVAL_STATE_RE.sub(marker, body)
    if updated_body == body:
        updated_body = f"{body.rstrip()}\n\n{marker}" if body.strip() else marker
    if updated_body != body:
        github.request("PATCH", f"/pulls/{number}", {"body": updated_body})


def sync_approvals(
    github: GitHubAPI,
    number: int,
    pull: dict[str, JsonValue],
    findings: list[Finding],
    command: QualityGraphCommand | None,
    author: str | None,
) -> tuple[set[str], bool, bool]:
    """Sync approvals and optional command modifications."""
    labels = github.paged(f"/issues/{number}/labels")
    finding_ids = {finding.finding_id for finding in findings}
    body = optional_string(pull.get("body")) or ""
    state_exists = APPROVAL_STATE_RE.search(body) is not None
    legacy_approved = {
        name[len(IGNORE_LABEL_PREFIX) :]
        for label in labels
        if (name := optional_string(label.get("name")))
        and name.startswith(IGNORE_LABEL_PREFIX)
        and name[len(IGNORE_LABEL_PREFIX) :] in finding_ids
    }
    for label in labels:
        name = optional_string(label.get("name"))
        if name and name.startswith(IGNORE_LABEL_PREFIX):
            github.request("DELETE", f"/issues/{number}/labels/{urllib.parse.quote(name, safe='')}")
    approved = (approval_state(body) if state_exists else legacy_approved) & finding_ids
    admin = command is not None and author is not None and is_admin(github, author)
    state_changed = False
    if not command or not admin:
        if not state_exists:
            update_approval_state(github, number, pull, approved)
        return approved, admin, state_changed
    name = command.name
    arguments = command.arguments
    if name in {"help", "status"}:
        return approved, admin, state_changed
    selected = {
        finding.finding_id
        for finding in findings
        if name == "ignore-file" and finding.path in arguments
    }
    if name in {"ignore", "remove-ignore"}:
        selected = (
            finding_ids
            if "object" in arguments
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
        state_changed = True
    update_approval_state(github, number, pull, approved)
    return approved, admin, state_changed


def sync_failure_label(github: GitHubAPI, number: int, *, has_active_findings: bool) -> None:
    """Set or clear failure label depending on active findings."""
    if has_active_findings:
        github.ensure_label(FAILURE_LABEL)
        github.request("POST", f"/issues/{number}/labels", {"labels": [FAILURE_LABEL]})
    else:
        github.request(
            "DELETE",
            f"/issues/{number}/labels/{urllib.parse.quote(FAILURE_LABEL, safe='')}",
        )


def is_admin(github: GitHubAPI, login: str) -> bool:
    """Check if login has admin rights on repository."""
    encoded = urllib.parse.quote(login, safe="")
    try:
        permission = github.request("GET", f"/collaborators/{encoded}/permission")
    except GitHubAPIError as error:
        if error.status == HTTP_FORBIDDEN:
            return False
        raise
    if permission is None:
        return False
    return json_object(permission, "collaborator permission").get("permission") == "admin"


def pull_request_number(event: dict[str, JsonValue]) -> int | None:
    """Extract pull request number from pull_request or issue event payload."""
    if event.get("pull_request"):
        pull = json_object(event["pull_request"], "event pull request")
        return json_integer(pull["number"], "pull request number")
    issue = json_object(event.get("issue", {}), "event issue")
    return json_integer(issue["number"], "issue number") if issue.get("pull_request") else None


def scan_pull_request(github: GitHub, pull: dict[str, JsonValue]) -> list[Finding]:
    """Scan pull request diff files for changed `object` annotations."""
    head = json_object(pull["head"], "pull request head")
    base = json_object(pull["base"], "pull request base")
    number = json_integer(pull["number"], "pull request number")
    head_sha = json_string(head["sha"], "head sha")
    base_sha = json_string(base["sha"], "base sha")
    files = github.paged(f"/pulls/{number}/files")
    raw_comparison = github.request("GET", f"/compare/{base_sha}...{head_sha}")
    if raw_comparison is None:
        message = f"Cannot determine merge base for pull request #{number}"
        raise RuntimeError(message)
    comparison = json_object(raw_comparison, "pull request comparison")
    merge_commit = json_object(comparison["merge_base_commit"], "merge base commit")
    merge_base = json_string(merge_commit["sha"], "merge base sha")
    findings: list[Finding] = []
    for file in files:
        path = json_string(file["filename"], "changed filename")
        if not path.endswith(".py") or file["status"] == "removed":
            continue
        source = github.file_text(path, head_sha)
        if source is None:
            message = f"Cannot read changed Python file {path} at {head_sha}"
            raise RuntimeError(message)
        patch = optional_string(file.get("patch"))
        if patch:
            changed = added_lines_from_patch(patch)
        else:
            before_path = optional_string(file.get("previous_filename")) or path
            before = github.file_text(before_path, merge_base)
            changed = changed_lines(before, source)
        findings.extend(scan_file(path, source, changed))
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.column))


def rerun_pull_request_gate(github: GitHub, number: int) -> None:
    """Rerun latest object annotation gate run for this pull request."""
    latest = latest_pull_request_run(github, number)
    if latest is None:
        message = f"Cannot find a previous gate run for pull request #{number}"
        raise RuntimeError(message)
    run_id = json_integer(latest["id"], "workflow run id")
    github.request("POST", f"/actions/runs/{run_id}/rerun-failed-jobs")


def latest_pull_request_run(github: GitHubAPI, number: int) -> dict[str, JsonValue] | None:
    """Return latest workflow run for the given pull request number."""
    for page in count(1):
        response = json_object(
            github.request(
                "GET",
                f"/actions/workflows/pr-checks.yaml/runs?event=pull_request"
                f"&per_page={WORKFLOW_RUNS_PER_PAGE}&page={page}",
            ),
            "workflow runs",
        )
        raw_runs = json_array(response.get("workflow_runs", []), "workflow runs")
        runs = [json_object(run, "workflow run") for run in raw_runs]
        matching = [
            run
            for run in runs
            if any(
                json_object(pull_request, "workflow pull request").get("number") == number
                for pull_request in json_array(
                    run.get("pull_requests", []), "workflow pull requests"
                )
            )
        ]
        if matching:
            return max(matching, key=lambda run: optional_string(run.get("created_at")) or "")
        if len(runs) < WORKFLOW_RUNS_PER_PAGE:
            return None
    message = "Workflow run pagination terminated unexpectedly"
    raise RuntimeError(message)


def main() -> int:
    """Run the Python object annotation gate for the current pull request event."""
    github = GitHub()
    event = json_object(
        decode_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()), "GitHub event"
    )
    number = pull_request_number(event)
    if number is None:
        return 0

    raw_pull = github.request("GET", f"/pulls/{number}")
    if raw_pull is None:
        message = f"Pull request #{number} was not found"
        raise RuntimeError(message)
    pull = json_object(raw_pull, "pull request")
    findings = scan_pull_request(github, pull)
    comment = json_object(event.get("comment", {}), "event comment")
    command = parse_command((optional_string(comment.get("body")) or "").strip())
    if command and validate_command(command) is not None:
        command = None
    if command and not command_targets_gate(command, "object"):
        command = None
    author_data = json_object(comment.get("user", {}), "comment user")
    author = json_string(author_data["login"], "comment author") if command else None
    approved, _, state_changed = sync_approvals(github, number, pull, findings, command, author)
    active = [finding for finding in findings if finding.finding_id not in approved]
    sync_failure_label(github, number, has_active_findings=bool(active))

    pr_url = json_string(pull["html_url"], "pull request URL")
    upsert_comment(
        github,
        number,
        "object-annotations",
        summary_body(findings, approved, pr_url),
    )
    if not findings:
        return 0

    if state_changed:
        rerun_pull_request_gate(github, number)
    if active:
        for finding in active:
            sys.stderr.write(
                f"::error file={finding.path},line={finding.line},"
                f"col={finding.column + 1}::Use a specific type instead of object\n"
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
