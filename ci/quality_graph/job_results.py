"""Model portable Quality Graph job results and GitHub annotations."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, cast

from monori.common import (
    JsonValue,
    array_value,
    integer_value,
    object_value,
    optional_string,
    string_value,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

MAX_STEP_ANNOTATIONS = 10
CONTROL_COMMAND_COUNT = 2
CONTROL_RE = re.compile(
    r"^- \[(?P<state>[ xX])] .*?<!-- monori-qg-control:(?P<payload>[A-Za-z0-9_-]+) -->$",
    re.MULTILINE,
)
ADMIN_DETAILS_RE = re.compile(
    r"\n?<details><summary>For repository administrators</summary>.*?</details>\n?",
    re.DOTALL,
)


class JobStatus(StrEnum):
    """Represent the dashboard state of one workflow job."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"

    @property
    def emoji(self) -> str:
        """Return the visual marker for this job state."""
        return {
            JobStatus.PENDING: "⏳",
            JobStatus.PASSED: "✅",
            JobStatus.FAILED: "❌",
            JobStatus.SKIPPED: "⏭️",
        }[self]


class AnnotationLevel(StrEnum):
    """Represent supported GitHub workflow annotation levels."""

    NOTICE = "notice"
    WARNING = "warning"
    FAILURE = "failure"

    @property
    def command(self) -> str:
        """Return the corresponding GitHub workflow command name."""
        return "error" if self is AnnotationLevel.FAILURE else self.value


@dataclass(frozen=True)
class JobMetric:
    """Store one compact metric for a dashboard or job summary."""

    label: str
    value: str


@dataclass(frozen=True)
class JobControl:
    """Store one reversible administrator command rendered as a checkbox."""

    command: str
    reverse_command: str
    checked: bool = False

    @property
    def marker(self) -> str:
        """Encode both canonical commands in a stable hidden marker."""
        payload = f"{self.command}\n{self.reverse_command}".encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        return f"monori-qg-control:{encoded}"


@dataclass(frozen=True)
class SourceAnnotation:
    """Describe one diagnostic tied to a trustworthy source range."""

    path: str
    start_line: int
    end_line: int
    message: str
    level: AnnotationLevel = AnnotationLevel.FAILURE
    title: str | None = None
    start_column: int | None = None
    end_column: int | None = None

    def __post_init__(self) -> None:
        """Reject ranges that GitHub cannot render safely."""
        if self.start_line < 1 or self.end_line < self.start_line:
            message = "Annotation line range must be positive and ordered"
            raise ValueError(message)
        if (self.start_column is None) != (self.end_column is None):
            message = "Annotation columns must be provided together"
            raise ValueError(message)
        if self.start_column is not None and (
            self.start_line != self.end_line
            or self.start_column < 1
            or cast("int", self.end_column) < self.start_column
        ):
            message = "Annotation columns require one positive ordered source line"
            raise ValueError(message)

    def to_json(self) -> dict[str, JsonValue]:
        """Serialize this annotation into the shared JSON value domain."""
        return {
            "path": self.path,
            "startLine": self.start_line,
            "endLine": self.end_line,
            "message": self.message,
            "level": self.level.value,
            "title": self.title,
            "startColumn": self.start_column,
            "endColumn": self.end_column,
        }

    @classmethod
    def from_json(cls, value: JsonValue) -> Self:
        """Deserialize and validate one source annotation."""
        data = object_value(value, "source annotation")
        start_column = data.get("startColumn")
        end_column = data.get("endColumn")
        return cls(
            string_value(data.get("path"), "annotation path"),
            integer_value(data.get("startLine"), "annotation start line"),
            integer_value(data.get("endLine"), "annotation end line"),
            string_value(data.get("message"), "annotation message"),
            AnnotationLevel(string_value(data.get("level"), "annotation level")),
            optional_string(data.get("title")),
            integer_value(start_column, "annotation start column")
            if start_column is not None
            else None,
            integer_value(end_column, "annotation end column") if end_column is not None else None,
        )


@dataclass(frozen=True)
class JobResult:
    """Carry one job's complete summary and compact dashboard data."""

    check_id: str
    title: str
    status: JobStatus
    summary: str = ""
    metrics: tuple[JobMetric, ...] = ()
    annotations: tuple[SourceAnnotation, ...] = ()
    controls: tuple[JobControl, ...] = ()
    control_notes: tuple[str, ...] = ()

    def to_json(self) -> dict[str, JsonValue]:
        """Serialize this result for transfer between isolated workflow jobs."""
        return {
            "checkId": self.check_id,
            "title": self.title,
            "status": self.status.value,
            "summary": self.summary,
            "metrics": [{"label": metric.label, "value": metric.value} for metric in self.metrics],
            "annotations": [annotation.to_json() for annotation in self.annotations],
            "controls": [
                {
                    "command": control.command,
                    "reverseCommand": control.reverse_command,
                    "checked": control.checked,
                }
                for control in self.controls
            ],
            "controlNotes": list(self.control_notes),
        }

    @classmethod
    def from_json(cls, value: JsonValue) -> Self:
        """Deserialize a job result produced by another runner."""
        data = object_value(value, "job result")
        metrics = tuple(
            JobMetric(
                string_value(item.get("label"), "metric label"),
                string_value(item.get("value"), "metric value"),
            )
            for raw in array_value(data.get("metrics", []), "job metrics")
            for item in (object_value(raw, "job metric"),)
        )
        controls = tuple(
            JobControl(
                string_value(item.get("command"), "control command"),
                string_value(item.get("reverseCommand"), "control reverse command"),
                item.get("checked") is True,
            )
            for raw in array_value(data.get("controls", []), "job controls")
            for item in (object_value(raw, "job control"),)
        )
        return cls(
            string_value(data.get("checkId"), "job check id"),
            string_value(data.get("title"), "job title"),
            JobStatus(string_value(data.get("status"), "job status")),
            string_value(data.get("summary", ""), "job summary"),
            metrics,
            tuple(
                SourceAnnotation.from_json(raw)
                for raw in array_value(data.get("annotations", []), "job annotations")
            ),
            controls,
            tuple(
                string_value(note, "control note")
                for note in array_value(data.get("controlNotes", []), "control notes")
            ),
        )


def grouped_annotations(
    annotations: Iterable[SourceAnnotation],
) -> tuple[SourceAnnotation, ...]:
    """Group diagnostics by source range and apply the GitHub step limit."""
    grouped: dict[
        tuple[str, int, int, AnnotationLevel, int | None, int | None],
        list[SourceAnnotation],
    ] = {}
    for annotation in annotations:
        key = (
            annotation.path,
            annotation.start_line,
            annotation.end_line,
            annotation.level,
            annotation.start_column,
            annotation.end_column,
        )
        grouped.setdefault(key, []).append(annotation)
    result: list[SourceAnnotation] = []
    for items in grouped.values():
        first = items[0]
        result.append(
            SourceAnnotation(
                first.path,
                first.start_line,
                first.end_line,
                "\n".join(dict.fromkeys(item.message for item in items)),
                first.level,
                first.title,
                first.start_column,
                first.end_column,
            )
        )
    return tuple(result[:MAX_STEP_ANNOTATIONS])


def controls_from_markdown(body: str) -> tuple[JobControl, ...]:
    """Recover typed controls from Markdown generated by the shared renderer."""
    controls: list[JobControl] = []
    for match in CONTROL_RE.finditer(body):
        encoded = match.group("payload")
        try:
            payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        except (ValueError, UnicodeDecodeError):
            continue
        commands = payload.splitlines()
        if len(commands) == CONTROL_COMMAND_COUNT:
            controls.append(
                JobControl(commands[0], commands[1], match.group("state").lower() == "x")
            )
    return tuple(controls)


def without_admin_controls(body: str) -> str:
    """Remove interactive controls from detailed Job Summary Markdown."""
    return ADMIN_DETAILS_RE.sub("\n", body).strip() + "\n"


def workflow_annotation_command(annotation: SourceAnnotation) -> str:
    """Render one escaped GitHub workflow annotation command."""
    properties = {
        "file": annotation.path,
        "line": str(annotation.start_line),
        "endLine": str(annotation.end_line),
    }
    if annotation.title is not None:
        properties["title"] = annotation.title
    if annotation.start_column is not None and annotation.end_column is not None:
        properties["col"] = str(annotation.start_column)
        properties["endColumn"] = str(annotation.end_column)
    encoded = ",".join(f"{key}={_escape_property(value)}" for key, value in properties.items())
    return f"::{annotation.level.command} {encoded}::{_escape_data(annotation.message)}"


def write_job_result(path: Path, result: JobResult) -> None:
    """Write one portable job result as deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_json(), indent=2, sort_keys=True) + "\n")


def read_job_result(path: Path) -> JobResult:
    """Read one portable job result from JSON."""
    return JobResult.from_json(cast("JsonValue", json.loads(path.read_text())))


def append_job_summary(path: Path, result: JobResult) -> None:
    """Append one complete job report to its GitHub summary file."""
    content = [
        f'<a id="quality-graph-{result.check_id}"></a>',
        "",
        f"## {result.status.emoji} Quality Graph · {result.check_id}",
        "",
        f"**{result.title}** — {result.status.value}",
    ]
    if result.metrics:
        content.extend(("", "| Metric | Value |", "| --- | ---: |"))
        content.extend(f"| {metric.label} | {metric.value} |" for metric in result.metrics)
    if result.summary:
        content.extend(("", result.summary.rstrip()))
    with path.open("a") as summary_file:
        summary_file.write("\n".join(content) + "\n")


def _escape_property(value: str) -> str:
    """Escape workflow-command property syntax."""
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def _escape_data(value: str) -> str:
    """Escape workflow-command message syntax."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
