"""Gate mutmut results against functions changed by the current diff."""

import argparse
import ast
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import override

from dulwich.graph import find_merge_base
from dulwich.objects import Commit
from dulwich.porcelain import diff_tree
from dulwich.repo import Repo

KILLED = {1, 3}
SURVIVED = 0
OTHER_STATUSES = {-24, 24, 35, 36, 152, 255}
CLASS_SEPARATOR = "ǁ"
MUTANT_SOURCE_PATHS = {
    "app/": "server/app/",
    "common/": "common/",
    "lib/": "ci/lib/",
    "quality_graph/": "ci/quality_graph/",
}
logger = logging.getLogger(__name__)


def append_step_summary(content: str) -> None:
    """Append step summary."""
    summary_path = os.environ.get("MUTATION_SUMMARY_PATH") or os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a") as summary:
            summary.write(content.rstrip() + "\n")


def parse_changed_lines(diff: str) -> dict[str, set[int]]:
    """Parse changed lines."""
    paths: dict[str, set[int]] = {}
    current: str | None = None
    new_line = 0
    deletion_only = False
    for line in diff.splitlines():
        if line == r"\ No newline at end of file":
            continue
        if line.startswith("+++ "):
            target = line[4:]
            if target == "/dev/null":
                current = None
                continue
            current = target.removeprefix("b/")
            paths.setdefault(current, set())
        elif line.startswith("@@"):
            hunk = line.split(" ", 3)[2]
            start, _, length = hunk[1:].partition(",")
            new_line = int(start)
            deletion_only = length == "0"
        elif current and line.startswith("+") and not line.startswith("+++"):
            paths[current].add(new_line)
            new_line += 1
        elif current and line.startswith("-") and not line.startswith("---"):
            paths[current].add(max(1, new_line if deletion_only else new_line - 1))
        elif current and new_line:
            new_line += 1
    return {path: lines for path, lines in paths.items() if lines}


def changed_lines(base: str) -> dict[str, set[int]]:
    """Read changed Python lines between the merge base and the current head."""
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
    return {
        path: lines
        for path, lines in parse_changed_lines(output.getvalue().decode()).items()
        if path.startswith(
            (
                "server/app/",
                "common/",
                "ci/lib/",
                "ci/quality_graph/",
            )
        )
    }


def commit_for_revision(repository: Repo, revision: str) -> Commit:
    """Resolve a git revision or remote branch name to a commit object."""
    candidates = (revision.encode(), f"refs/remotes/{revision}".encode())
    for candidate in candidates:
        try:
            resolved = repository[candidate]
        except KeyError:
            continue
        if isinstance(resolved, Commit):
            return resolved
    message = f"Cannot resolve git revision {revision}"
    raise RuntimeError(message)


class ChangedFunctions(ast.NodeVisitor):
    """Collect Python functions and methods touched by a unified diff."""

    def __init__(self, changed: set[int]) -> None:
        """Store changed line references for change collection."""
        self.changed = changed
        self.classes: list[str] = []
        self.functions: set[tuple[str, str | None]] = set()

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        end = node.end_lineno or node.lineno
        if any(line in self.changed for line in range(node.lineno, end + 1)):
            self.functions.add((node.name, self.classes[-1] if self.classes else None))
        self.generic_visit(node)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def changed_functions(
    root: Path, lines_by_path: dict[str, set[int]]
) -> dict[str, set[tuple[str, str | None]]]:
    """Collect functions changed in the given diff."""
    result: dict[str, set[tuple[str, str | None]]] = {}
    for path, lines in lines_by_path.items():
        source_path = root / path
        if not source_path.exists() or source_path.suffix != ".py":
            continue
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        collector = ChangedFunctions(lines)
        collector.visit(tree)
        if collector.functions:
            result[path] = collector.functions
    return result


def mutant_function(key: str) -> tuple[str, str | None]:
    """Mutant function for this module."""
    original = key.partition("__mutmut_")[0].rsplit(".", 1)[-1]
    if CLASS_SEPARATOR in original:
        parts = original.split(CLASS_SEPARATOR)
        return parts[-1].removeprefix("x_"), parts[-2]
    return original.removeprefix("x_"), None


def source_path_for_mutant(relative_path: Path) -> str | None:
    """Map a mutmut metadata path to its configured source path."""
    relative_source = str(relative_path)[:-5]
    for mutant_prefix, source_prefix in MUTANT_SOURCE_PATHS.items():
        if relative_source.startswith(mutant_prefix):
            return f"{source_prefix}{relative_source.removeprefix(mutant_prefix)}"
    return None


def load_meta(path: Path) -> dict[str, int | None]:
    """Load meta."""
    data = json.loads(path.read_text())
    statuses = data.get("exit_code_by_key")
    if not isinstance(statuses, dict):
        message = f"mutation-diff: invalid mutmut metadata in {path}: missing exit_code_by_key"
        raise TypeError(message)
    return dict(statuses)


@dataclass(frozen=True)
class GateRequest:
    """Inputs required to evaluate changed Python mutants."""

    mutants_dir: Path
    baseline_dir: Path
    root: Path
    base: str
    threshold: float
    skip_new_survivors: bool


@dataclass
class MutationStats:
    """Aggregate verdict inputs collected from relevant mutmut metadata."""

    killed: int = 0
    survived: int = 0
    other: int = 0
    new_survivors: int = 0
    survivor_keys: list[str] = field(default_factory=list)
    no_coverage_keys: list[str] = field(default_factory=list)

    @property
    def considered(self) -> int:
        """Return the number of mutants included in the score."""
        return self.killed + self.survived + self.other


def record_mutant(
    stats: MutationStats,
    key: str,
    status: int | None,
    baseline: dict[str, int | None],
) -> None:
    """Classify one mutant result and update aggregate mutation statistics."""
    if status is None:
        stats.other += 1
        stats.no_coverage_keys.append(key)
    elif status == SURVIVED:
        stats.survived += 1
        stats.survivor_keys.append(key)
        if baseline.get(key) != SURVIVED:
            stats.new_survivors += 1
    elif status in KILLED:
        stats.killed += 1
    elif status in OTHER_STATUSES:
        stats.other += 1


def collect_mutation_stats(
    request: GateRequest,
    functions: dict[str, set[tuple[str, str | None]]],
) -> MutationStats:
    """Collect mutation statuses for functions changed by the current diff."""
    stats = MutationStats()
    for meta_path in request.mutants_dir.rglob("*.py.meta"):
        relative = meta_path.relative_to(request.mutants_dir)
        source_path = source_path_for_mutant(relative)
        if source_path is None or (allowed := functions.get(source_path)) is None:
            continue
        baseline_path = request.baseline_dir / relative
        baseline = load_meta(baseline_path) if baseline_path.exists() else {}
        for key, status in load_meta(meta_path).items():
            if mutant_function(key) in allowed:
                record_mutant(stats, key, status, baseline)
    return stats


def append_empty_summary(message: str) -> int:
    """Publish a passing summary when no mutants are eligible for scoring."""
    logger.info("mutation-diff: %s — pass", message)
    append_step_summary(f"## Python mutation diff\n\n{message.capitalize()} — **pass**.")
    return 0


def gate_python(
    request: GateRequest,
) -> int:
    """Evaluate changed Python mutants and return the gate exit code."""
    functions = changed_functions(request.root, changed_lines(request.base))
    if not functions:
        return append_empty_summary("no changed Python functions")
    stats = collect_mutation_stats(request, functions)
    if stats.considered == 0:
        return append_empty_summary("changed functions have no tested mutants")
    return report_verdict(request, stats)


def report_verdict(request: GateRequest, stats: MutationStats) -> int:
    """Publish the mutation verdict and return its process exit code."""
    score = 100 * stats.killed / stats.considered
    passed = score >= request.threshold and (request.skip_new_survivors or stats.new_survivors == 0)
    gate_status = "✅ PASS" if passed else "❌ FAIL"
    summary = [
        "## Python mutation diff",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Status | {gate_status} |",
        f"| Killed | {stats.killed} |",
        f"| Survived | {stats.survived} |",
        f"| No coverage | {len(stats.no_coverage_keys)} |",
        f"| New survivors | {stats.new_survivors} |",
        f"| Considered | {stats.considered} |",
        f"| Score | {score:.2f}% |",
        f"| Threshold | {request.threshold:.0f}% |",
    ]
    if stats.survivor_keys:
        summary.extend(["", "<details>", "<summary>Surviving mutants</summary>", ""])
        summary.extend(f"- `{key}`" for key in stats.survivor_keys)
        summary.extend(["", "</details>"])
    if stats.no_coverage_keys:
        summary.extend(["", "<details>", "<summary>Mutants without coverage</summary>", ""])
        summary.extend(f"- `{key}`" for key in stats.no_coverage_keys)
        summary.extend(["", "</details>"])
    append_step_summary("\n".join(summary))
    return 0 if passed else 1


gate_backend = gate_python


def main() -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutants", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--skip-new-survivors", action="store_true")
    args = parser.parse_args()
    return gate_python(
        GateRequest(
            args.mutants,
            args.baseline,
            Path.cwd(),
            args.base,
            args.threshold,
            args.skip_new_survivors,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
