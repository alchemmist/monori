"""Parse source diagnostics emitted by project development tools."""

from __future__ import annotations

import re
from dataclasses import dataclass

from monori.ci.lib.annotations import AnnotationLevel, SourceAnnotation

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
COLON_RE = re.compile(
    r"^(?P<path>[^:\n]+\.(?:py|pyi|ts|tsx|js|jsx|css|html|sql|ya?ml|md|toml|jsonc?))"
    r":(?P<line>\d+)(?::(?P<column>\d+))?(?::|\s+-)\s*(?P<message>.+)$"
)
PAREN_RE = re.compile(
    r"^(?P<path>[^()\n]+\.(?:ts|tsx|js|jsx))"
    r"\((?P<line>\d+),(?P<column>\d+)\):\s*(?P<message>.+)$"
)
POSITION_RE = re.compile(r"^(?P<line>\d+):(?P<column>\d+)\s+(?P<message>(?:error|warning)\s+.+)$")
FILE_RE = re.compile(r"^(?P<path>.+\.(?:py|pyi|ts|tsx|js|jsx|css|html|sql|ya?ml|md|toml|jsonc?))$")
SQLFLUFF_PATH_RE = re.compile(r"^== \[(?P<path>.+)] FAIL$")
SQLFLUFF_DIAGNOSTIC_RE = re.compile(
    r"^L:\s*(?P<line>\d+)\s*\|\s*P:\s*(?P<column>\d+)\s*\|\s*"
    r"(?P<code>\S+)\s*\|\s*(?P<message>.+)$"
)
BANDIT_LOCATION_RE = re.compile(r"^Location:\s+(?P<path>.+\.py):(?P<line>\d+):(?P<column>\d+)$")
BANDIT_ISSUE_RE = re.compile(r"^>> Issue:\s*(?P<message>.+)$")
SEMGREP_ISSUE_RE = re.compile(r"^\u276f\u2771\s*(?P<message>.+)$")
SEMGREP_LINE_RE = re.compile(r"^(?P<line>\d+)┆")
DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(?P<path>.+)$")
DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<line>\d+)(?:,(?P<count>\d+))? @@")


@dataclass(frozen=True)
class DiagnosticContext:
    """Carry state needed by multiline diagnostic formats."""

    path: str | None = None
    message: str | None = None


def parse_diagnostics(log: str) -> tuple[SourceAnnotation, ...]:
    """Extract source annotations from supported compiler, linter, and test output."""
    annotations: list[SourceAnnotation] = []
    context = DiagnosticContext()
    for raw_line in ANSI_RE.sub("", log).splitlines():
        line = raw_line.strip()
        context, contextual_annotation, handled = parse_context_line(line, context)
        if contextual_annotation is not None:
            annotations.append(contextual_annotation)
        if handled:
            continue
        match = COLON_RE.match(line) or PAREN_RE.match(line)
        if match is not None:
            annotations.append(annotation_from_match(match.group("path"), match))
            continue
        position_match = POSITION_RE.match(line)
        if position_match is not None and context.path is not None:
            annotations.append(annotation_from_match(context.path, position_match))
    return tuple(dict.fromkeys(annotations))


def parse_context_line(
    line: str, context: DiagnosticContext
) -> tuple[DiagnosticContext, SourceAnnotation | None, bool]:
    """Parse one line from a stateful multiline diagnostic format."""
    file_match = FILE_RE.match(line) or SQLFLUFF_PATH_RE.match(line)
    if file_match is not None:
        updated = DiagnosticContext(
            normalize_source_path(file_match.group("path")), context.message
        )
        return updated, None, True
    issue_match = BANDIT_ISSUE_RE.match(line) or SEMGREP_ISSUE_RE.match(line)
    if issue_match is not None:
        return DiagnosticContext(context.path, issue_match.group("message")), None, True
    sqlfluff_match = SQLFLUFF_DIAGNOSTIC_RE.match(line)
    if sqlfluff_match is not None and context.path is not None:
        annotation = annotation_from_match(
            context.path, sqlfluff_match, title=sqlfluff_match.group("code")
        )
        return context, annotation, True
    bandit_match = BANDIT_LOCATION_RE.match(line)
    if bandit_match is not None and context.message is not None:
        annotation = annotation_from_match(
            bandit_match.group("path"), bandit_match, message=context.message
        )
        return context, annotation, True
    semgrep_line = SEMGREP_LINE_RE.match(line)
    if semgrep_line is not None and context.path is not None:
        source_line = int(semgrep_line.group("line"))
        annotation = SourceAnnotation(
            context.path,
            source_line,
            source_line,
            context.message or "Static analysis finding",
        )
        return context, annotation, True
    return context, None, False


def annotation_from_match(
    path: str,
    match: re.Match[str],
    *,
    message: str | None = None,
    title: str | None = None,
) -> SourceAnnotation:
    """Convert a regex match with line metadata into a typed annotation."""
    line = int(match.group("line"))
    raw_column = match.groupdict().get("column")
    column = int(raw_column) if raw_column is not None else None
    annotation_message = message or match.groupdict().get("message") or "Source diagnostic"
    return SourceAnnotation(
        normalize_source_path(path),
        line,
        line,
        annotation_message.strip(),
        AnnotationLevel.FAILURE,
        title=title,
        start_column=column,
        end_column=column,
    )


def normalize_source_path(path: str) -> str:
    """Convert absolute runner paths into repository-relative annotation paths."""
    for root in ("common/", "ci/", "server/", "web/"):
        marker = f"/{root}"
        position = path.rfind(marker)
        if position >= 0:
            return path[position + 1 :]
    return path.removeprefix("./")


def parse_diff_annotations(diff: str) -> tuple[SourceAnnotation, ...]:
    """Convert changed formatter hunks into precise source annotations."""
    annotations: list[SourceAnnotation] = []
    path: str | None = None
    for line in diff.splitlines():
        file_match = DIFF_FILE_RE.match(line)
        if file_match is not None:
            path = file_match.group("path")
            continue
        hunk_match = DIFF_HUNK_RE.match(line)
        if hunk_match is None or path is None:
            continue
        start_line = int(hunk_match.group("line"))
        count = int(hunk_match.group("count") or "1")
        if count == 0:
            continue
        annotations.append(
            SourceAnnotation(
                path,
                start_line,
                start_line + count - 1,
                "This source range is not formatted.",
                title="Formatting",
            )
        )
    return tuple(annotations)
