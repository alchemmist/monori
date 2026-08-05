"""Check changed Python annotations for uses of the overly broad ``object`` type."""

import ast
import difflib
import hashlib
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, override

from monori.ci.lib.github import GitHub, RepositoryGitHubAPI, rerun_latest_pull_request_workflow
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

PATCH_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
IGNORE_LABEL_PREFIX = "monori-object-annotation-ignore-"
FINDING_ID_PREFIX = "object-"
FAILURE_LABEL = "monori-object-annotation-failed"
APPROVAL_STATE_RE = re.compile(r"<!-- monori-object-annotation-approvals: ([0-9a-f,]*) -->")
APPROVALS = ApprovalLifecycle(
    "object",
    FINDING_ID_PREFIX,
    APPROVAL_STATE_RE,
    "<!-- monori-object-annotation-approvals: {ids} -->",
    legacy_label_prefix=IGNORE_LABEL_PREFIX,
    allow_file_commands=True,
)


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


class ObjectAnnotationCheck(PullRequestSourceCheck[Finding]):
    """Find changed annotations that use the overly broad ``object`` type."""

    gate = "object"
    report_marker = "object-annotations"
    approval_lifecycle = APPROVALS
    supports_ignore_file = True
    failure_label: ClassVar[str | None] = FAILURE_LABEL

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

    @override
    def collect_pull_request(
        self, github: RepositoryGitHubAPI, pull: dict[str, JsonValue]
    ) -> list[Finding]:
        """Collect changed object annotations from the pull request."""
        return scan_pull_request(github, pull)

    @override
    def render_summary(
        self, findings: list[Finding], approved: set[str], pull_request_url: str
    ) -> str:
        """Render the object-annotation report."""
        return summary_body(findings, approved, pull_request_url)

    @override
    def error_annotation(self, finding: Finding) -> str:
        """Render an error annotation for an overly broad type."""
        return (
            f"::error file={finding.path},line={finding.line},col={finding.column + 1}::"
            "Use a specific type instead of object"
        )

    @override
    def rerun(self, github: RepositoryGitHubAPI, number: int) -> None:
        """Rerun the pull-request workflow after approvals change."""
        rerun_latest_pull_request_workflow(github, number)


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


def scan_pull_request(github: RepositoryGitHubAPI, pull: dict[str, JsonValue]) -> list[Finding]:
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


def main() -> int:
    """Run the Python object annotation gate for the current pull request event."""
    github = GitHub()
    event = object_value(
        decode_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()), "GitHub event"
    )
    return ObjectAnnotationCheck().run_pull_request_gate(github, event)


if __name__ == "__main__":
    raise SystemExit(main())
