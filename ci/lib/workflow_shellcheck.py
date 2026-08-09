"""Extract shell scripts embedded in GitHub Actions YAML files."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

EXPRESSION_RE = re.compile(r"\$\{\{.*?}}", re.DOTALL)


@dataclass(frozen=True)
class EmbeddedScript:
    """Identify one shell script by its YAML file and ordinal position."""

    path: Path
    ordinal: int
    source: str


def embedded_scripts(path: Path) -> tuple[EmbeddedScript, ...]:
    """Extract Bash-compatible `run` steps from a workflow or composite action."""
    document = yaml.compose(path.read_text(), Loader=yaml.SafeLoader)
    sources: list[str] = []

    def visit(node: yaml.Node) -> None:
        if isinstance(node, yaml.MappingNode):
            values = {
                key.value: value for key, value in node.value if isinstance(key, yaml.ScalarNode)
            }
            source = values.get("run")
            shell = values.get("shell")
            shell_name = shell.value.split()[0] if isinstance(shell, yaml.ScalarNode) else "bash"
            if isinstance(source, yaml.ScalarNode) and shell_name in {"bash", "sh"}:
                sources.append(source.value)
            for child in values.values():
                visit(child)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                visit(child)

    if document is not None:
        visit(document)
    return tuple(
        EmbeddedScript(path, ordinal, source) for ordinal, source in enumerate(sources, start=1)
    )


def write_scripts(paths: list[Path], output: Path) -> None:
    """Write every embedded shell step to an individual ShellCheck input file."""
    output.mkdir(parents=True, exist_ok=True)
    scripts = (script for path in paths for script in embedded_scripts(path))
    for index, script in enumerate(scripts, start=1):
        source_name = script.path.as_posix().replace("/", "-").lstrip(".")
        destination = output / f"{index:04}-{source_name}-step-{script.ordinal}.sh"
        source = EXPRESSION_RE.sub("${GITHUB_ACTION_EXPRESSION}", script.source)
        destination.write_text(source)


def main() -> int:
    """Extract embedded shell scripts from the supplied GitHub Actions files."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("paths", nargs="+", type=Path)
    arguments = parser.parse_args()
    write_scripts(arguments.paths, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
