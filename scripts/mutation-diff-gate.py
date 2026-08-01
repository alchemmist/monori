"""Gate mutmut results against functions changed by the current diff."""

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

KILLED = {1, 3}
SURVIVED = 0
CONSIDERED = KILLED | {SURVIVED, -24, 24, 35, 36, 152, 255}
CLASS_SEPARATOR = "ǁ"


def changed_lines(base: str) -> dict[str, set[int]]:
    result = subprocess.run(
        ["git", "diff", "--unified=0", f"{base}...HEAD", "--", "server/app"],
        check=True,
        capture_output=True,
        text=True,
    )
    paths: dict[str, set[int]] = {}
    current: str | None = None
    new_line = 0
    for line in result.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            paths.setdefault(current, set())
        elif line.startswith("@@"):
            hunk = line.split(" ", 3)[2]
            start, _, length = hunk[1:].partition(",")
            new_line = int(start)
            if length and length != "0":
                new_line = int(start)
        elif current and line.startswith("+") and not line.startswith("+++"):
            paths[current].add(new_line)
            new_line += 1
        elif current and line.startswith("-") and not line.startswith("---"):
            continue
        elif current and new_line:
            new_line += 1
    return {path: lines for path, lines in paths.items() if lines}


class ChangedFunctions(ast.NodeVisitor):
    def __init__(self, changed: set[int]) -> None:
        self.changed = changed
        self.classes: list[str] = []
        self.functions: set[tuple[str, str | None]] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        end = node.end_lineno or node.lineno
        if any(line in self.changed for line in range(node.lineno, end + 1)):
            self.functions.add((node.name, self.classes[-1] if self.classes else None))
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


def changed_functions(root: Path, lines_by_path: dict[str, set[int]]) -> dict[str, set[tuple[str, str | None]]]:
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
    return {key: value for key, value in data["exit_code_by_key"].items()}


def gate_backend(
    mutants_dir: Path,
    baseline_dir: Path,
    root: Path,
    base: str,
    threshold: float,
) -> int:
    line_changes = changed_lines(base)
    functions = changed_functions(root, line_changes)
    if not functions:
        print("mutation-diff: no changed backend functions — pass")
        return 0

    killed = survived = other = new_survivors = 0
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
            if mutant_function(key) not in allowed or status is None:
                continue
            if status == SURVIVED:
                survived += 1
                if baseline.get(key) != SURVIVED:
                    new_survivors += 1
            elif status in KILLED:
                killed += 1
            elif status in CONSIDERED:
                other += 1

    considered = killed + survived + other
    if considered == 0:
        print("mutation-diff: changed functions have no tested mutants — pass")
        return 0
    score = 100 * killed / considered
    passed = score >= threshold and new_survivors == 0
    print("── changed backend mutation summary ─────────────────")
    print(f"killed             {killed}")
    print(f"survived           {survived}")
    print(f"new survivors      {new_survivors}")
    print(f"considered         {considered}")
    print(f"score              {score:.2f}%")
    print(f"threshold          {threshold:.0f}%")
    print(f"mutation-diff gate {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutants", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--threshold", type=float, required=True)
    args = parser.parse_args()
    return gate_backend(args.mutants, args.baseline, Path.cwd(), args.base, args.threshold)


if __name__ == "__main__":
    sys.exit(main())
