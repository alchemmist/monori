"""Build the pull-request coverage gate report."""

from __future__ import annotations

import argparse
import ast
import html
import json
import math
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from dulwich.graph import find_merge_base
from dulwich.objects import Commit
from dulwich.porcelain import diff_tree
from dulwich.repo import Repo
from pydantic import ConfigDict, Field, TypeAdapter
from pydantic.dataclasses import dataclass as pydantic_dataclass

from monori.ci.lib.mutation_diff_gate import commit_for_revision, parse_changed_lines
from monori.common import array_value, decode_json, integer_value, number_value, object_value

if TYPE_CHECKING:
    from collections.abc import Iterable

    from monori.common import JsonValue

SCHEMA_VERSION: Literal[1] = 1
PATCH_THRESHOLD = 100.0
STACK_PATHS: dict[Literal["backend", "frontend"], tuple[str, ...]] = {
    "backend": ("server/app", "common"),
    "frontend": ("web/src",),
}


@pydantic_dataclass(config=ConfigDict(extra="forbid", strict=True))
class Finding:
    """Describe one uncovered source range."""

    path: Annotated[str, Field(max_length=500)]
    function: Annotated[str, Field(max_length=200)]
    start: Annotated[int, Field(ge=1)]
    end: Annotated[int, Field(ge=1)]


@pydantic_dataclass(config=ConfigDict(extra="forbid", strict=True))
class StackReport:
    """Describe coverage for one independently gated stack."""

    name: Literal["backend", "frontend"]
    touched: bool
    total: Annotated[float, Field(ge=0, le=100)]
    patch: Annotated[float, Field(ge=0, le=100)]
    covered_lines: Annotated[int, Field(ge=0)]
    changed_lines: Annotated[int, Field(ge=0)]
    findings: Annotated[list[Finding], Field(max_length=5000)]
    baseline: Annotated[float | None, Field(ge=0, le=100)] = None
    error: Annotated[str | None, Field(max_length=500)] = None

    @property
    def regressed(self) -> bool:
        """Return whether total coverage fell below the trusted baseline."""
        return self.baseline is not None and self.total < self.baseline

    @property
    def passed(self) -> bool:
        """Return whether this stack satisfies both coverage signals."""
        return not self.touched or (
            self.error is None and self.patch >= PATCH_THRESHOLD and not self.regressed
        )


@pydantic_dataclass(config=ConfigDict(extra="forbid", strict=True))
class CoverageReport:
    """Validate the complete untrusted coverage artifact."""

    schema_version: Literal[1]
    coverage_ok: bool
    stacks: Annotated[list[StackReport], Field(min_length=2, max_length=2)]

    def __post_init__(self) -> None:
        """Require exactly one report for each supported stack."""
        if {stack.name for stack in self.stacks} != set(STACK_PATHS):
            message = "Coverage artifact must contain backend and frontend stacks"
            raise ValueError(message)

    @property
    def passed(self) -> bool:
        """Return the aggregate gate verdict."""
        return self.coverage_ok and all(stack.passed for stack in self.stacks)


COVERAGE_REPORT_ADAPTER = TypeAdapter(CoverageReport)


def load_json(path: Path) -> JsonValue:
    """Load one JSON document."""
    return decode_json(path.read_bytes())


def coverage_totals(frontend: Path, backend: Path) -> dict[str, float]:
    """Read per-stack line percentages from native coverage summaries."""
    front = object_value(load_json(frontend), "frontend coverage")
    front_total = object_value(front.get("total"), "frontend total")
    front_lines = object_value(front_total.get("lines"), "frontend lines")
    back = object_value(load_json(backend), "backend coverage")
    back_totals = object_value(back.get("totals"), "backend totals")
    return {
        "frontend": float(number_value(front_lines.get("pct"), "frontend line percent")),
        "backend": float(number_value(back_totals.get("percent_covered"), "backend line percent")),
    }


def write_baseline(frontend: Path, backend: Path, output: Path) -> None:
    """Write the trusted main-branch total coverage baseline."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "stacks": coverage_totals(frontend, backend)},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def load_baseline(path: Path) -> dict[str, float] | None:
    """Load a complete trusted main-branch baseline."""
    if not path.is_file():
        return None
    try:
        root = object_value(load_json(path), "coverage baseline")
        if root.get("schema_version") != SCHEMA_VERSION:
            message = "Coverage baseline schema is unsupported"
            raise ValueError(message)
        stacks = object_value(root.get("stacks"), "baseline stacks")
        if set(stacks) != set(STACK_PATHS):
            message = "Coverage baseline must contain backend and frontend stacks"
            raise ValueError(message)
        result: dict[str, float] = {
            name: float(number_value(stacks.get(name), f"{name} baseline")) for name in STACK_PATHS
        }
    except (json.JSONDecodeError, TypeError) as error:
        message = "Coverage baseline is invalid"
        raise ValueError(message) from error
    if any(
        not math.isfinite(value) or not 0 <= value <= PATCH_THRESHOLD for value in result.values()
    ):
        message = "Coverage baseline values must be finite percentages"
        raise ValueError(message)
    return result


def normalize_lcov(source: Path, output: Path) -> None:
    """Make frontend LCOV paths relative to the repository root."""
    lines = []
    for source_line in source.read_text().splitlines():
        normalized = source_line
        if source_line.startswith("SF:"):
            path = source_line[3:]
            if path.startswith("src/"):
                normalized = f"SF:web/{path}"
        lines.append(normalized)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")


def changed_paths(base: str) -> set[str]:
    """Read paths changed between the merge base and the current head."""
    repository = Repo(Path.cwd())
    head = commit_for_revision(repository, "HEAD")
    base_commit = commit_for_revision(repository, base)
    merge_bases = find_merge_base(repository, [base_commit.id, head.id])
    if not merge_bases:
        message = f"Cannot find merge base for {base} and HEAD"
        raise RuntimeError(message)
    merge_base = repository[merge_bases[0]]
    if not isinstance(merge_base, Commit):
        message = f"Merge base for {base} and HEAD is not a commit"
        raise TypeError(message)
    output = BytesIO()
    diff_tree(repository, merge_base.tree, head.tree, output)
    return set(parse_changed_lines(output.getvalue().decode()))


def stack_touched(paths: Iterable[str], changed: set[str]) -> bool:
    """Return whether source files for a stack changed in the pull request."""
    return any(path.startswith(tuple(f"{prefix}/" for prefix in paths)) for path in changed)


def python_function(path: Path, line: int) -> str:
    """Resolve an uncovered Python line to its narrowest enclosing function."""
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError):
        return "(module)"
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.lineno <= line <= (node.end_lineno or node.lineno)
    ]
    if not matches:
        return "(module)"
    return max(matches, key=lambda node: node.lineno).name


TS_FUNCTION_PATTERNS = (
    re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=.*(?:=>|function\b)"),
    re.compile(r"^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^;]*\)\s*\{"),
)
TS_NON_FUNCTIONS = {"if", "for", "while", "switch", "catch"}


def typescript_function(path: Path, line: int) -> str:
    """Resolve a TypeScript line to the nearest preceding function declaration."""
    try:
        source = path.read_text().splitlines()
    except OSError:
        return "(module)"
    for candidate in reversed(source[:line]):
        for pattern in TS_FUNCTION_PATTERNS:
            match = pattern.search(candidate)
            if match is not None and match.group(1) not in TS_NON_FUNCTIONS:
                return match.group(1)
    return "(module)"


def function_name(path: str, line: int) -> str:
    """Resolve an uncovered line to a best-effort source function name."""
    source = Path(path)
    if source.suffix == ".py":
        return python_function(source, line)
    return typescript_function(source, line)


def group_findings(raw: dict[str, JsonValue]) -> list[Finding]:
    """Group consecutive uncovered lines by file and function."""
    src_stats = object_value(raw.get("src_stats", {}), "diff-cover src_stats")
    findings: list[Finding] = []
    for path, entry in sorted(src_stats.items()):
        stats = object_value(entry, f"diff-cover stats for {path}")
        lines = sorted(
            line
            for line in array_value(stats.get("violation_lines", []), path)
            if isinstance(line, int)
        )
        current: Finding | None = None
        for line in lines:
            name = function_name(path, line)
            if current is not None and current.function == name and line == current.end + 1:
                current = Finding(
                    path=current.path,
                    function=current.function,
                    start=current.start,
                    end=line,
                )
                findings[-1] = current
            else:
                current = Finding(path=path, function=name, start=line, end=line)
                findings.append(current)
    return findings


def diff_stats(path: Path) -> tuple[float, int, int, list[Finding], str | None]:
    """Read one diff-cover JSON report or return a bounded infrastructure error."""
    if not path.is_file():
        return 0, 0, 0, [], "Diff coverage report was not produced"
    try:
        raw = object_value(load_json(path), str(path))
        changed = integer_value(raw.get("total_num_lines"), "changed coverage lines")
        violations = integer_value(raw.get("total_num_violations"), "uncovered changed lines")
        patch = float(number_value(raw.get("total_percent_covered"), "patch coverage"))
        return patch, changed - violations, changed, group_findings(raw), None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return 0, 0, 0, [], f"Invalid diff coverage report: {error}"


@dataclass(frozen=True)
class ReportInputs:
    """Collect filesystem and workflow inputs for one report build."""

    frontend: Path
    backend: Path
    frontend_diff: Path
    backend_diff: Path
    baseline_path: Path
    base: str
    coverage_exit: int


def build_report(inputs: ReportInputs) -> CoverageReport:
    """Build the validated artifact consumed by the privileged reporter."""
    totals = coverage_totals(inputs.frontend, inputs.backend)
    baseline = load_baseline(inputs.baseline_path)
    changed_files = changed_paths(inputs.base)
    diff_paths = {"frontend": inputs.frontend_diff, "backend": inputs.backend_diff}
    stacks = []
    for name, paths in STACK_PATHS.items():
        patch, covered, changed_count, findings, error = diff_stats(diff_paths[name])
        touched = stack_touched(paths, changed_files)
        stacks.append(
            StackReport(
                name=name,
                touched=touched,
                total=totals[name],
                baseline=None if baseline is None else baseline[name],
                patch=patch if touched else 100,
                covered_lines=covered if touched else 0,
                changed_lines=changed_count if touched else 0,
                findings=findings if touched else [],
                error=error if touched else None,
            )
        )
    return CoverageReport(
        schema_version=SCHEMA_VERSION,
        coverage_ok=inputs.coverage_exit == 0,
        stacks=stacks,
    )


def write_report(report: CoverageReport, output: Path) -> None:
    """Write a deterministic coverage artifact."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(COVERAGE_REPORT_ADAPTER.dump_json(report, indent=2) + b"\n")


def percent(value: float) -> str:
    """Format a coverage percentage compactly."""
    return f"{value:.2f}%"


def markdown_cell(value: str) -> str:
    """Render untrusted artifact text as one inert Markdown table cell."""
    single_line = value.replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    return html.escape(single_line.replace("`", "'"))


def failure_reasons(report: CoverageReport, *, workflow_passed: bool) -> list[str]:
    """Explain every active aggregate coverage failure."""
    touched = [stack for stack in report.stacks if stack.touched]
    reasons = []
    if not workflow_passed or not report.coverage_ok:
        reasons.append("the coverage job or an existing absolute coverage floor failed")
    if any(stack.regressed for stack in touched):
        reasons.append("total coverage dropped relative to `main`")
    if any(stack.patch < PATCH_THRESHOLD for stack in touched):
        reasons.append("new or changed executable lines are not covered")
    if any(stack.error is not None for stack in touched):
        reasons.append("coverage evidence was incomplete")
    return reasons or ["the coverage verdict was unavailable"]


def render_summary(report: CoverageReport, *, workflow_passed: bool) -> str:
    """Render the detailed coverage job summary."""
    passed = workflow_passed and report.passed
    touched = [stack for stack in report.stacks if stack.touched]
    if passed:
        summary = "✅ New code covered, total coverage did not drop — all good.\n"
        if any(stack.baseline is None for stack in touched):
            summary += (
                "\n⚠️ Total-coverage regression gate inactive: "
                "the base coverage baseline was unavailable.\n"
            )
        return summary
    lines = ["## ❌ Coverage", "", "This check failed because:"]
    lines.extend(
        f"- {reason}" for reason in failure_reasons(report, workflow_passed=workflow_passed)
    )
    lines.extend(["", "| Stack | Total | Delta | Patch |", "| --- | ---: | ---: | ---: |"])
    for stack in touched:
        delta = "baseline unavailable"
        if stack.baseline is not None:
            delta = f"{stack.total - stack.baseline:+.2f}%"
        patch = f"{stack.covered_lines}/{stack.changed_lines} ({percent(stack.patch)})"
        lines.append(f"| {stack.name} | {percent(stack.total)} | {delta} | {patch} |")
    findings = [finding for stack in touched for finding in stack.findings]
    if findings:
        lines.extend(
            [
                "",
                "Add tests that execute these changed lines:",
                "",
                "| File | Function | Uncovered lines |",
                "| --- | --- | ---: |",
            ]
        )
        for finding in findings:
            line_range = str(finding.start)
            if finding.end != finding.start:
                line_range = f"{finding.start}-{finding.end}"
            path = markdown_cell(finding.path)
            function = markdown_cell(finding.function)
            lines.append(f"| `{path}` | `{function}` | {line_range} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Run coverage artifact lifecycle operations."""
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    baseline = commands.add_parser("baseline")
    baseline.add_argument("--frontend", type=Path, required=True)
    baseline.add_argument("--backend", type=Path, required=True)
    baseline.add_argument("--output", type=Path, required=True)

    normalize = commands.add_parser("normalize-lcov")
    normalize.add_argument("--input", type=Path, required=True)
    normalize.add_argument("--output", type=Path, required=True)

    report = commands.add_parser("report")
    report.add_argument("--frontend", type=Path, required=True)
    report.add_argument("--backend", type=Path, required=True)
    report.add_argument("--frontend-diff", type=Path, required=True)
    report.add_argument("--backend-diff", type=Path, required=True)
    report.add_argument("--baseline", type=Path, required=True)
    report.add_argument("--base", required=True)
    report.add_argument("--coverage-exit", type=int, required=True)
    report.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "baseline":
        write_baseline(args.frontend, args.backend, args.output)
        return 0
    if args.command == "normalize-lcov":
        normalize_lcov(args.input, args.output)
        return 0
    built = build_report(
        ReportInputs(
            frontend=args.frontend,
            backend=args.backend,
            frontend_diff=args.frontend_diff,
            backend_diff=args.backend_diff,
            baseline_path=args.baseline,
            base=args.base,
            coverage_exit=args.coverage_exit,
        )
    )
    write_report(built, args.output)
    return 0 if built.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
