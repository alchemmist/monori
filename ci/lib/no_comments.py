"""
Command-line check that rejects inline comments outside allowed markers.

The module scans Python files for comment tokens and reports violations when a
comment is not an approved formatter, security, or typing directive.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import tokenize
from pathlib import Path

ALLOWED_COMMENT = re.compile(r"^#\s*(?:noqa|nosec|type:\s*(?:ignore|noqa))\b", re.IGNORECASE)
logger = logging.getLogger(__name__)


def python_files(root: Path) -> list[Path]:
    """Return sorted Python files below a root, excluding generated and virtual environments."""
    return sorted(
        path
        for path in root.rglob("*.py")
        if not any(part in {".venv", "__pycache__", "mutants"} for part in path.parts)
    )


def violations(path: Path) -> list[tuple[int, int, str]]:
    """Return line, column, and text for comments not covered by the allowed directives."""
    result = []
    with tokenize.open(path) as source:
        for token in tokenize.generate_tokens(source.readline):
            if token.type != tokenize.COMMENT:
                continue
            text = token.string
            if text.startswith("#!") or ALLOWED_COMMENT.match(text):
                continue
            result.append((token.start[0], token.start[1] + 1, text))
    return result


def main(argv: list[str] | None = None) -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", type=Path, nargs="+")
    args = parser.parse_args(argv)

    found = False
    for root in args.roots:
        for path in python_files(root):
            for line, column, text in violations(path):
                found = True
                logger.error("%s:%s:%s: code comment is not allowed: %s", path, line, column, text)
    return int(found)


if __name__ == "__main__":
    sys.exit(main())
