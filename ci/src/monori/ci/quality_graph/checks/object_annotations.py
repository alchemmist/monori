"""Check changed Python annotations for uses of the overly broad ``object`` type."""

import ast
import difflib
import hashlib
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import override

from monori.ci.lib.github import (
    GITHUB_PAGE_SIZE,
    GitHub,
    RepositoryGitHubAPI,
    sync_label,
)
from monori.ci.quality_graph.base import ApprovalLifecycle, ApprovalRequest, QualityCheck
from monori.ci.quality_graph.commands import (
    QualityGraphCommand,
    command_request,
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

PATCH_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
IGNORE_LABEL_PREFIX = "monori-object-annotation-ignore-"
FINDING_ID_PREFIX = "object-"
FAILURE_LABEL = "monori-object-annotation-failed"
APPROVAL_STATE_RE = re.compile(r"<!-- monori-object-annotation-approvals: ([0-9a-f,]*) -->")
WORKFLOW_RUNS_PER_PAGE = GITHUB_PAGE_SIZE
APPROVALS = ApprovalLifecycle(
    "object",
    FINDING_ID_PREFIX,
    APPROVAL_STATE_RE,
    "<!-- monori-object-annotation-approvals: {ids} -->",
    legacy_label_prefix=IGNORE_LABEL_PREFIX,
)


@dataclass(frozen=True)
class Finding:
    """Object-type finding location and associated detection metadata."""

    path: str
    line: int
    column: int
    annotation: str
    finding_id: str


@dataclass(frozen=True)
class SyncApprovalCommandState:
    """Input state for an approval-sync command."""

    command: QualityGraphCommand | None
    author: str | None


def display_finding_id(finding_id: str) -> str:
    """Return finding id prefixed for command addressing."""
    return f"{FINDING_ID_PREFIX}{finding_id}"


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
    report_marker = "object-annotations"
    approval_lifecycle = APPROVALS

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


def summary_body(findings: list[Finding], approved: set[str], pr_url: str) -> str:
    """Render the summary markdown shown for object annotation check."""
    active = [finding for finding in findings if finding.finding_id not in approved]
    return render_report(
        ReportModel(
            "object-annotations",
            ReportStatus.DONE if not active else ReportStatus.FAIL,
            metrics=(
                ReportMetric("Status", "PASS" if not active else "FAIL"),
                ReportMetric("Findings", str(len(findings))),
                ReportMetric("Active", str(len(active))),
                ReportMetric("Approved", str(len(findings) - len(active))),
            ),
            findings_title="List of problems",
            findings=tuple(
                ReportFinding(
                    f"`{finding.annotation}` · `{display_finding_id(finding.finding_id)}`",
                    approved=finding.finding_id in approved,
                    location=finding_location(pr_url, finding.path, finding.line),
                )
                for finding in findings
            ),
            admin=admin_commands(
                "object",
                [display_finding_id(finding.finding_id) for finding in active],
                [
                    display_finding_id(finding.finding_id)
                    for finding in findings
                    if finding.finding_id in approved
                ],
                [finding.path for finding in active],
            ),
        )
    )


def sync_approvals(
    github: RepositoryGitHubAPI,
    number: int,
    pull: dict[str, JsonValue],
    findings: list[Finding],
    command_state: SyncApprovalCommandState,
) -> tuple[set[str], bool, bool]:
    """Sync approvals and optional command modifications."""
    body = optional_string(pull.get("body")) or ""
    request = ApprovalRequest(
        github,
        number,
        body,
        command_state.command,
        command_state.author,
        github.paged(f"/issues/{number}/labels"),
    )
    result = ObjectAnnotationCheck().sync_approvals(
        request,
        findings,
    )
    return result.approved, result.authorized, result.changed


def pull_request_number(event: dict[str, JsonValue]) -> int | None:
    """Extract pull request number from pull_request or issue event payload."""
    if event.get("pull_request"):
        pull = object_value(event["pull_request"], "event pull request")
        return integer_value(pull["number"], "pull request number")
    issue = object_value(event.get("issue", {}), "event issue")
    return integer_value(issue["number"], "issue number") if issue.get("pull_request") else None


def scan_pull_request(github: GitHub, pull: dict[str, JsonValue]) -> list[Finding]:
    """Scan pull request diff files for changed `object` annotations."""
    head = object_value(pull["head"], "pull request head")
    base = object_value(pull["base"], "pull request base")
    number = integer_value(pull["number"], "pull request number")
    head_sha = string_value(head["sha"], "head sha")
    base_sha = string_value(base["sha"], "base sha")
    files = github.paged(f"/pulls/{number}/files")
    raw_comparison = github.request("GET", f"/compare/{base_sha}...{head_sha}")
    if raw_comparison is None:
        message = f"Cannot determine merge base for pull request #{number}"
        raise RuntimeError(message)
    comparison = object_value(raw_comparison, "pull request comparison")
    merge_commit = object_value(comparison["merge_base_commit"], "merge base commit")
    merge_base = string_value(merge_commit["sha"], "merge base sha")
    findings: list[Finding] = []
    for file in files:
        path = string_value(file["filename"], "changed filename")
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
    run_id = integer_value(latest["id"], "workflow run id")
    github.request("POST", f"/actions/runs/{run_id}/rerun-failed-jobs")


def latest_pull_request_run(
    github: RepositoryGitHubAPI, number: int
) -> dict[str, JsonValue] | None:
    """Return latest workflow run for the given pull request number."""
    for page in count(1):
        response = object_value(
            github.request(
                "GET",
                f"/actions/workflows/pr-checks.yaml/runs?event=pull_request"
                f"&per_page={WORKFLOW_RUNS_PER_PAGE}&page={page}",
            ),
            "workflow runs",
        )
        raw_runs = array_value(response.get("workflow_runs", []), "workflow runs")
        runs = [object_value(run, "workflow run") for run in raw_runs]
        matching = [
            run
            for run in runs
            if any(
                object_value(pull_request, "workflow pull request").get("number") == number
                for pull_request in array_value(
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
    event = object_value(
        decode_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()), "GitHub event"
    )
    number = pull_request_number(event)
    if number is None:
        return 0

    report = ObjectAnnotationCheck().report(github, number)
    report.mark_in_progress()

    raw_pull = github.request("GET", f"/pulls/{number}")
    if raw_pull is None:
        message = f"Pull request #{number} was not found"
        raise RuntimeError(message)
    pull = object_value(raw_pull, "pull request")
    findings = scan_pull_request(github, pull)
    request = command_request(event)
    command = parse_command(request.body) if request is not None else None
    if command and validate_command(command) is not None:
        command = None
    if command and not command_targets_gate(command, "object"):
        command = None
    author = request.login if command and request is not None else None
    approved, _, state_changed = sync_approvals(
        github,
        number,
        pull,
        findings,
        SyncApprovalCommandState(command, author),
    )
    active = [finding for finding in findings if finding.finding_id not in approved]
    sync_label(github, number, FAILURE_LABEL, present=bool(active))

    pr_url = string_value(pull["html_url"], "pull request URL")
    report.publish(summary_body(findings, approved, pr_url))
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
