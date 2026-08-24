"""
Reject newly introduced Python casts and TypeScript type assertions.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal, override

from dulwich.repo import Repo

from monori.ci.lib.annotations import AnnotationLevel, SourceAnnotation
from monori.ci.lib.findings import stable_finding_id
from monori.ci.quality_graph.base import (
    ApprovalLifecycle,
    PullRequestSourceCheck,
    QualityRuntime,
    read_github_event,
)
from monori.ci.quality_graph.checks.object_annotations import (
    added_lines_from_patch,
    changed_lines,
)
from monori.ci.quality_graph.models import CheckContext, CheckResult, Metric, Verdict
from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.reporting import (
    RenderedCheckReport,
    ReportFinding,
    ReportModel,
    ReportStatus,
    admin_commands,
    finding_location,
    render_report,
)
from monori.common import JsonValue, integer_value, object_value, optional_string, string_value

if TYPE_CHECKING:
    from monori.ci.lib.github import RepositoryGitHubAPI

Language = Literal["python", "typescript"]
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".mts", ".cts"}
TYPESCRIPT_SUFFIXES = {".ts", ".tsx", ".mts", ".cts"}
GENERATED_PARTS = {"build", "dist", "generated", "node_modules", "static", "mutants"}
FINDING_ID_PREFIX = "cast-"
FAILURE_LABEL = "monori-type-cast-failed"
APPROVAL_STATE_RE = re.compile(r"<!-- monori-type-cast-approvals: ([0-9a-f,]*) -->")
APPROVALS = ApprovalLifecycle(
    "cast",
    FINDING_ID_PREFIX,
    APPROVAL_STATE_RE,
    "<!-- monori-type-cast-approvals: {ids} -->",
    allow_file_commands=True,
)
TOKEN_RE = re.compile(
    r"(?P<identifier>[A-Za-z_$][\w$]*)|(?P<number>\d+(?:\.\d+)?)|"
    r"(?P<operator>=>|===|!==|==|!=|<=|>=|\?\?|&&|\|\||\+\+|--|\.\.\.|.)",
    re.DOTALL,
)
NON_CODE_RE = re.compile(
    r"//[^\n]*|/\*[\s\S]*?\*/|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`"
)
JSX_TEXT_RE = re.compile(r"(?<=>)[^<{]+(?=<)")
ASSERTION_BOUNDARIES = {";", ",", ")", "}", "=", "=>", "&&", "||", "??"}
ANGLE_PREFIXES = {"=", "(", "[", "{", ",", ":", ";", "!", "&&", "||", "??", "=>"}


@dataclass(frozen=True)
class Finding:
    """
    Describe one cast with enough detail for reports and suppressions.
    """

    path: str
    line: int
    column: int
    language: Language
    cast_form: str
    suggestion: str
    finding_id: str


@dataclass(frozen=True)
class Token:
    """
    Store one TypeScript token and its source location.
    """

    value: str
    start: int
    end: int
    line: int
    column: int


def display_finding_id(finding_id: str) -> str:
    """
    Return a command-addressable finding identifier.
    """
    return f"{FINDING_ID_PREFIX}{finding_id}"


def is_generated(path: str, source: str) -> bool:
    """
    Return whether a source file is generated and outside the gate's scope.
    """
    parts = set(Path(path).parts)
    header = "\n".join(source.splitlines()[:3]).lower()
    return bool(parts & GENERATED_PARTS) or "@generated" in header or "code generated" in header


def python_cast_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """
    Resolve direct and module-qualified names that definitely refer to typing.cast.
    """
    direct: set[str] = set()
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"typing", "typing_extensions"}:
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module in {"typing", "typing_extensions"}:
            for alias in node.names:
                if alias.name == "cast":
                    direct.add(alias.asname or alias.name)
    return direct, modules


def python_cast_form(call: ast.Call, direct: set[str], modules: set[str]) -> str | None:
    """
    Return the resolved cast form for a Python call, if it is typing.cast.
    """
    function = call.func
    if isinstance(function, ast.Name) and function.id in direct:
        return function.id
    if (
        isinstance(function, ast.Attribute)
        and function.attr == "cast"
        and isinstance(function.value, ast.Name)
        and function.value.id in modules
    ):
        return f"{function.value.id}.cast"
    return None


def parent_nodes(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """
    Index AST parents for lexical binding checks.
    """
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def function_scope(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    """
    Return the nearest function-like scope containing a node.
    """
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return current
        current = parents.get(current)
    return None


def name_is_shadowed(
    tree: ast.Module,
    call: ast.Call,
    name: str,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    """
    Check whether a local or later module binding replaces an imported cast name.
    """
    scope = function_scope(call, parents)
    for node in ast.walk(scope or tree):
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Store):
            continue
        if node.id != name or function_scope(node, parents) is not scope:
            continue
        if scope is not None or (node.lineno, node.col_offset) < (call.lineno, call.col_offset):
            return True
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        arguments = [*scope.args.posonlyargs, *scope.args.args, *scope.args.kwonlyargs]
        arguments.extend(
            argument for argument in (scope.args.vararg, scope.args.kwarg) if argument is not None
        )
        return any(argument.arg == name for argument in arguments)
    return False


def scan_python(path: str, source: str, selected_lines: set[int]) -> list[Finding]:
    """
    Find resolved typing.cast calls on selected Python lines.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    direct, modules = python_cast_names(tree)
    parents = parent_nodes(tree)
    candidates: list[tuple[int, int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        form = python_cast_form(node, direct, modules)
        if form is None:
            continue
        root_name = form.split(".", maxsplit=1)[0]
        if name_is_shadowed(tree, node, root_name, parents):
            continue
        rendered = ast.get_source_segment(source, node) or form
        identity = f"{path}:python:{' '.join(rendered.split())}"
        candidates.append((node.lineno, node.col_offset, form, identity))
    findings = build_findings(
        path,
        "python",
        candidates,
        "Narrow the type or validate at a boundary",
    )
    return [finding for finding in findings if finding.line in selected_lines]


def mask_typescript_non_code(source: str) -> str:
    """
    Mask comments and string literals while preserving offsets and newlines.
    """
    masked = NON_CODE_RE.sub(
        lambda match: "".join("\n" if character == "\n" else " " for character in match.group()),
        source,
    )
    output = list(masked)
    for start, end in template_expression_ranges(source):
        output[start:end] = mask_typescript_non_code(source[start:end])
    return "".join(output)


def template_expression_ranges(source: str) -> list[tuple[int, int]]:
    """
    Locate code regions embedded in template literals.
    """
    ranges: list[tuple[int, int]] = []
    index = 0
    while index < len(source):
        if source[index] != "`":
            index += 1
            continue
        index += 1
        while index < len(source) and source[index] != "`":
            if source[index] == "\\":
                index += 2
                continue
            if source.startswith("${", index):
                end = matching_template_brace(source, index + 2)
                ranges.append((index + 2, end))
                index = end + 1
                continue
            index += 1
        index += 1
    return ranges


def matching_template_brace(source: str, start: int) -> int:
    """
    Find the closing brace of one template interpolation.
    """
    depth = 1
    index = start
    quote: str | None = None
    while index < len(source):
        character = source[index]
        if quote is not None:
            if character == "\\":
                index += 2
                continue
            if character == quote:
                quote = None
        elif character in {"'", '"'}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return len(source)


def typescript_tokens(source: str, *, jsx: bool) -> list[Token]:
    """
    Tokenize masked TypeScript source with precise one-based locations.
    """
    masked = mask_typescript_non_code(source)
    if jsx:
        masked = JSX_TEXT_RE.sub(
            lambda match: "".join(
                "\n" if character == "\n" else " " for character in match.group()
            ),
            masked,
        )
    tokens: list[Token] = []
    for match in TOKEN_RE.finditer(masked):
        value = match.group()
        if value.isspace():
            continue
        start = match.start()
        line_start = source.rfind("\n", 0, start) + 1
        tokens.append(
            Token(
                value,
                start,
                match.end(),
                source.count("\n", 0, start) + 1,
                start - line_start + 1,
            )
        )
    return tokens


def is_non_assertion_as(tokens: list[Token], index: int) -> bool:
    """
    Exclude aliases, properties, and mapped-type remapping syntax.
    """
    if index + 1 < len(tokens) and tokens[index + 1].value == ":":
        return True
    statement_start = max(
        (candidate + 1 for candidate in range(index) if tokens[candidate].value == ";"),
        default=0,
    )
    statement = [token.value for token in tokens[statement_start:index]]
    if statement[:1] == ["import"]:
        return True
    if statement[:1] == ["export"] and "{" in statement and "=" not in statement:
        return True
    bracket_start = max(
        (candidate for candidate in range(index) if tokens[candidate].value == "["),
        default=-1,
    )
    bracket_end = max(
        (candidate for candidate in range(index) if tokens[candidate].value == "]"),
        default=-1,
    )
    return bracket_start > bracket_end and any(
        token.value == "in" for token in tokens[bracket_start:index]
    )


def assertion_end(tokens: list[Token], start: int) -> int:
    """
    Find a conservative end token for an `as Type` assertion.
    """
    depth = 0
    end = start
    for index in range(start, len(tokens)):
        value = tokens[index].value
        if value in {"<", "[", "("}:
            depth += 1
        elif value in {">", "]", ")"}:
            if depth == 0:
                break
            depth -= 1
        if index > start and depth == 0 and value in ASSERTION_BOUNDARIES:
            break
        if index > start and tokens[index].line != tokens[start].line and depth == 0:
            break
        end = index
    return end


def is_jsx_text(source: str, token: Token) -> bool:
    """
    Return whether a token is plain text between JSX tags rather than code.
    """
    prefix = source[: token.start]
    opening = prefix.rfind("<")
    closing = prefix.rfind(">")
    if closing < opening:
        return False
    tail = prefix[closing + 1 :]
    return tail.count("{") == tail.count("}")


def scan_typescript(path: str, source: str, selected_lines: set[int]) -> list[Finding]:
    """
    Find TypeScript `as` and angle-bracket assertions on selected lines.
    """
    tokens = typescript_tokens(source, jsx=Path(path).suffix == ".tsx")
    candidates: list[tuple[int, int, str, str]] = []
    for index, token in enumerate(tokens):
        if (
            token.value == "as"
            and index + 1 < len(tokens)
            and not is_non_assertion_as(tokens, index)
            and not (Path(path).suffix == ".tsx" and is_jsx_text(source, token))
        ):
            if tokens[index + 1].value == "const":
                continue
            end = assertion_end(tokens, index + 1)
            form = source[token.start : tokens[end].end].strip()
            identity = f"{path}:typescript:{' '.join(form.split())}"
            candidates.append((token.line, token.column - 1, form, identity))
        elif token.value == "<" and Path(path).suffix != ".tsx":
            previous = tokens[index - 1].value if index else None
            if previous is not None and previous not in ANGLE_PREFIXES and previous != "return":
                continue
            closing = next(
                (
                    candidate
                    for candidate in range(index + 2, len(tokens))
                    if tokens[candidate].value == ">" and tokens[candidate].line == token.line
                ),
                None,
            )
            if closing is None or closing + 1 >= len(tokens):
                continue
            type_tokens = tokens[index + 1 : closing]
            remaining_line = source[tokens[closing].end :].split("\n", maxsplit=1)[0]
            if any(item.value == "extends" for item in type_tokens) or (
                tokens[closing + 1].value == "(" and "=>" in remaining_line
            ):
                continue
            if not type_tokens or not any(
                re.match(r"[A-Za-z_$]", item.value) for item in type_tokens
            ):
                continue
            form = source[token.start : tokens[closing].end].strip()
            identity = f"{path}:typescript:{' '.join(form.split())}"
            candidates.append((token.line, token.column - 1, form, identity))
    findings = build_findings(
        path,
        "typescript",
        candidates,
        "Narrow the value or validate it before use",
    )
    return [finding for finding in findings if finding.line in selected_lines]


def build_findings(
    path: str,
    language: Language,
    candidates: list[tuple[int, int, str, str]],
    suggestion: str,
) -> list[Finding]:
    """
    Assign stable, collision-safe identities to scanner candidates.
    """
    duplicates = Counter(identity for _, _, _, identity in candidates)
    findings = []
    for line, column, form, identity in candidates:
        disambiguator = f":{line}:{column}" if duplicates[identity] > 1 else ""
        findings.append(
            Finding(
                path,
                line,
                column,
                language,
                form,
                suggestion,
                stable_finding_id(identity, disambiguator),
            )
        )
    return sorted(findings, key=lambda finding: (finding.line, finding.column, finding.cast_form))


def scan_file(path: str, source: str, selected_lines: set[int]) -> list[Finding]:
    """
    Scan one supported, non-generated source file.
    """
    if is_generated(path, source):
        return []
    suffix = Path(path).suffix
    if suffix == ".py":
        return scan_python(path, source, selected_lines)
    if suffix in TYPESCRIPT_SUFFIXES:
        return scan_typescript(path, source, selected_lines)
    return []


class TypeCastCheck(PullRequestSourceCheck[Finding]):
    """
    Find newly introduced Python and TypeScript casts.
    """

    definition = WORKFLOW_JOB_BY_ID["type-casts"]
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
        return CheckResult(findings, Verdict.FAIL if findings else Verdict.PASS)

    @override
    def collect_pull_request(
        self, github: RepositoryGitHubAPI, pull: dict[str, JsonValue]
    ) -> list[Finding]:
        return scan_pull_request(github, pull)

    @override
    def render_summary(
        self, findings: list[Finding], approved: set[str], pull_request_url: str
    ) -> RenderedCheckReport:
        return summary_body(findings, approved, pull_request_url)

    @override
    def source_annotation(self, finding: Finding) -> SourceAnnotation:
        return SourceAnnotation(
            finding.path,
            finding.line,
            finding.line,
            f"{finding.cast_form}: {finding.suggestion} ({display_finding_id(finding.finding_id)})",
            AnnotationLevel.FAILURE,
            start_column=finding.column + 1,
            end_column=finding.column + max(1, len(finding.cast_form)),
        )


def summary_body(findings: list[Finding], approved: set[str], pr_url: str) -> RenderedCheckReport:
    """
    Render all casts, including approved exceptions, in the job report.
    """
    active = [finding for finding in findings if finding.finding_id not in approved]
    return render_report(
        ReportModel(
            "type-casts",
            ReportStatus.PASSED if not active else ReportStatus.FAILED,
            metrics=(
                Metric("Status", "PASS" if not active else "FAIL"),
                Metric("Findings", str(len(findings))),
                Metric("Active", str(len(active))),
                Metric("Approved", str(len(findings) - len(active))),
            ),
            findings_title="Unsafe type casts",
            findings=tuple(
                ReportFinding(
                    f"`{finding.language}` · `{finding.cast_form}` · "
                    f"{finding.suggestion} · `{display_finding_id(finding.finding_id)}`",
                    approved=finding.finding_id in approved,
                    location=finding_location(pr_url, finding.path, finding.line),
                )
                for finding in findings
            ),
            admin=admin_commands(
                "cast",
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
    """
    Scan only added or replaced lines in supported pull-request files.
    """
    head = object_value(pull["head"], "pull request head")
    base = object_value(pull["base"], "pull request base")
    number = integer_value(pull["number"], "pull request number")
    head_sha = string_value(head["sha"], "head sha")
    base_sha = string_value(base["sha"], "base sha")
    files = github.paged(f"/pulls/{number}/files")
    comparison = object_value(
        github.request("GET", f"/compare/{base_sha}...{head_sha}"),
        "pull request comparison",
    )
    merge_base = string_value(
        object_value(comparison["merge_base_commit"], "merge base commit")["sha"],
        "merge base sha",
    )
    findings: list[Finding] = []
    for file in files:
        path = string_value(file["filename"], "changed filename")
        if Path(path).suffix not in SOURCE_SUFFIXES or file["status"] == "removed":
            continue
        source = github.file_text(path, head_sha)
        if source is None:
            message = f"Cannot read changed source file {path} at {head_sha}"
            raise RuntimeError(message)
        patch = optional_string(file.get("patch"))
        if patch:
            selected = added_lines_from_patch(patch)
        else:
            previous_path = optional_string(file.get("previous_filename")) or path
            selected = changed_lines(github.file_text(previous_path, merge_base), source)
        findings.extend(scan_file(path, source, selected))
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.column))


def scan_repository(root: Path) -> list[Finding]:
    """
    Scan every tracked source file for scheduled and manual checks.
    """
    findings = []
    repository = Repo.discover(str(root))
    tracked = sorted(path.decode() for path in repository.open_index())
    for relative in tracked:
        if Path(relative).suffix not in SOURCE_SUFFIXES:
            continue
        source = (root / relative).read_text()
        findings.extend(scan_file(relative, source, set(range(1, source.count("\n") + 2))))
    return findings


def repository_main(arguments: list[str]) -> int:
    """
    Run a full repository scan and optionally emit deterministic JSON.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail", action="store_true")
    options = parser.parse_args(arguments)
    findings = scan_repository(Path.cwd())
    report = json.dumps([asdict(finding) for finding in findings], indent=2, sort_keys=True) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(report)
    else:
        sys.stdout.write(report)
    return 1 if findings and options.fail else 0


def main() -> int:
    """
    Run the pull-request gate or an explicit full repository scan.
    """
    if "--all" in sys.argv[1:]:
        arguments = [argument for argument in sys.argv[1:] if argument != "--all"]
        return repository_main(arguments)
    runtime = QualityRuntime.from_environment()
    return TypeCastCheck().run_pull_request_gate(
        runtime.github,
        read_github_event(),
        runtime.publisher,
        read_only=runtime.read_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
