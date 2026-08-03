"""Gate mutmut results against functions changed by the current diff."""

import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import override

# mutmut >=3.6.0 stores pytest exit codes in .py.meta files:
# 0 means survived, 1/3 means killed, and the remaining values below are
# timeout or suspicious outcomes that still belong in the score denominator.
KILLED = {1, 3}
SURVIVED = 0
OTHER_STATUSES = {-24, 24, 35, 36, 152, 255}
CLASS_SEPARATOR = "ǁ"


def append_step_summary(content: str) -> None:
    summary_path = os.environ.get("MUTATION_SUMMARY_PATH") or os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a") as summary:
            summary.write(content.rstrip() + "\n")


def parse_changed_lines(diff: str) -> dict[str, set[int]]:
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
    result = subprocess.run(
        ["git", "diff", "--unified=0", f"{base}...HEAD", "--", "server/app"],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_changed_lines(result.stdout)


class ChangedFunctions(ast.NodeVisitor):
    def __init__(self, changed: set[int]) -> None:
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
    original = key.partition("__mutmut_")[0].rsplit(".", 1)[-1]
    if CLASS_SEPARATOR in original:
        parts = original.split(CLASS_SEPARATOR)
        return parts[-1].removeprefix("x_"), parts[-2]
    return original.removeprefix("x_"), None


def load_meta(path: Path) -> dict[str, int | None]:
    data = json.loads(path.read_text())
    statuses = data.get("exit_code_by_key")
    if not isinstance(statuses, dict):
        raise TypeError(
            f"mutation-diff: invalid mutmut metadata in {path}: missing exit_code_by_key"
        )
    return dict(statuses)


def gate_backend(
    mutants_dir: Path,
    baseline_dir: Path,
    root: Path,
    base: str,
    threshold: float,
    skip_new_survivors: bool,
) -> int:
    line_changes = changed_lines(base)
    functions = changed_functions(root, line_changes)
    if not functions:
        print("mutation-diff: no changed backend functions — pass")
        append_step_summary("## Backend mutation diff\n\nNo changed backend functions — **pass**.")
        return 0

    killed = survived = other = new_survivors = 0
    survivor_keys: list[str] = []
    no_coverage_keys: list[str] = []
    for meta_path in mutants_dir.rglob("*.py.meta"):
        relative = meta_path.relative_to(mutants_dir)
        source_path = f"server/{str(relative)[:-5]}"  # remove .meta
        allowed = functions.get(source_path)
        if not allowed:
            continue
        current = load_meta(meta_path)
        baseline_path = baseline_dir / relative
        baseline = load_meta(baseline_path) if baseline_path.exists() else {}
        for key, status in current.items():
            if mutant_function(key) not in allowed:
                continue
            if status is None:
                other += 1
                no_coverage_keys.append(key)
            elif status == SURVIVED:
                survived += 1
                survivor_keys.append(key)
                if baseline.get(key) != SURVIVED:
                    new_survivors += 1
            elif status in KILLED:
                killed += 1
            elif status in OTHER_STATUSES:
                other += 1

    considered = killed + survived + other
    if considered == 0:
        print("mutation-diff: changed functions have no tested mutants — pass")
        append_step_summary(
            "## Backend mutation diff\n\nChanged functions have no tested mutants — **pass**."
        )
        return 0
    score = 100 * killed / considered
    passed = score >= threshold and (skip_new_survivors or new_survivors == 0)
    gate_status = "✅ PASS" if passed else "❌ FAIL"
    print("── changed backend mutation summary ─────────────────")
    print(f"killed             {killed}")
    print(f"survived           {survived}")
    print(f"new survivors      {new_survivors}")
    print(f"considered         {considered}")
    print(f"score              {score:.2f}%")
    print(f"threshold          {threshold:.0f}%")
    print(f"mutation-diff gate {'PASS' if passed else 'FAIL'}")
    summary = [
        "## Backend mutation diff",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Status | {gate_status} |",
        f"| Killed | {killed} |",
        f"| Survived | {survived} |",
        f"| No coverage | {len(no_coverage_keys)} |",
        f"| New survivors | {new_survivors} |",
        f"| Considered | {considered} |",
        f"| Score | {score:.2f}% |",
        f"| Threshold | {threshold:.0f}% |",
    ]
    if survivor_keys:
        summary.extend(["", "<details>", "<summary>Surviving mutants</summary>", ""])
        summary.extend(f"- `{key}`" for key in survivor_keys)
        summary.extend(["", "</details>"])
    if no_coverage_keys:
        summary.extend(["", "<details>", "<summary>Mutants without coverage</summary>", ""])
        summary.extend(f"- `{key}`" for key in no_coverage_keys)
        summary.extend(["", "</details>"])
    append_step_summary("\n".join(summary))
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutants", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--skip-new-survivors", action="store_true")
    args = parser.parse_args()
    return gate_backend(
        args.mutants,
        args.baseline,
        Path.cwd(),
        args.base,
        args.threshold,
        args.skip_new_survivors,
    )


if __name__ == "__main__":
    sys.exit(main())
