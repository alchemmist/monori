"""Create and publish source annotations independently of a CI workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, cast

from monori.common import JsonValue, integer_value, object_value, optional_string, string_value

if TYPE_CHECKING:
    from collections.abc import Iterable

MAX_STEP_ANNOTATIONS = 10


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
    encoded = ",".join(f"{key}={escape_property(value)}" for key, value in properties.items())
    return f"::{annotation.level.command} {encoded}::{escape_data(annotation.message)}"


def escape_property(value: str) -> str:
    """Escape one GitHub workflow-command property value."""
    return escape_data(value).replace(":", "%3A").replace(",", "%2C")


def escape_data(value: str) -> str:
    """Escape one GitHub workflow-command message value."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
