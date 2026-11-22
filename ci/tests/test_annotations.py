# Copyright (c) 2026
from dataclasses import replace
from io import StringIO

import pytest

from monori.ci.lib.annotations import (
    MAX_STEP_ANNOTATIONS,
    AnnotationLevel,
    SourceAnnotation,
    escape_data,
    grouped_annotations,
    publish_workflow_annotations,
    workflow_annotation_command,
)


def test_annotation_validates_ranges_and_round_trips_json() -> None:
    annotation = SourceAnnotation("a.py", 2, 2, "bad", start_column=3, end_column=5)
    assert SourceAnnotation.from_json(annotation.to_json()) == annotation
    with pytest.raises(ValueError, match="line range"):
        SourceAnnotation("a.py", 0, 1, "bad")
    with pytest.raises(ValueError, match="provided together"):
        SourceAnnotation("a.py", 1, 1, "bad", start_column=1)
    with pytest.raises(ValueError, match="positive ordered"):
        SourceAnnotation("a.py", 1, 2, "bad", start_column=2, end_column=1)


def test_grouped_annotations_merge_locations_and_limit_output() -> None:
    annotations = [
        SourceAnnotation("same.py", 1, 1, "first"),
        SourceAnnotation("same.py", 1, 1, "second"),
        *(SourceAnnotation(f"file-{index}.py", 1, 1, "failure") for index in range(20)),
    ]
    grouped = grouped_annotations(annotations)
    assert len(grouped) == MAX_STEP_ANNOTATIONS
    assert grouped[0].message == "first\nsecond"


def test_workflow_commands_escape_and_publish_omission_notice() -> None:
    annotation = SourceAnnotation(
        "a,b.py",
        1,
        1,
        "line one\nline two",
        AnnotationLevel.WARNING,
        title="bad:title",
        start_column=2,
        end_column=4,
    )
    assert workflow_annotation_command(annotation) == (
        "::warning file=a%2Cb.py,line=1,endLine=1,title=bad%3Atitle,col=2,endColumn=4::"
        "line one%0Aline two"
    )
    assert AnnotationLevel.FAILURE.command == "error"
    assert escape_data("100%\r\nnext") == "100%25%0D%0Anext"
    stream = StringIO()
    publish_workflow_annotations(
        [annotation, annotation], omitted_message="More findings", stream=stream
    )
    assert "::notice::More findings" in stream.getvalue()

    overflow = StringIO()
    publish_workflow_annotations(
        [
            SourceAnnotation(f"file-{index}.py", 1, 1, "failure")
            for index in range(MAX_STEP_ANNOTATIONS + 1)
        ],
        omitted_message="More findings",
        stream=overflow,
    )
    assert "::notice::More findings" in overflow.getvalue()


@pytest.mark.parametrize(
    ("start", "end", "start_column", "end_column", "error"),
    [
        (2, 1, None, None, "line range"),
        (1, 1, None, 1, "provided together"),
        (1, 1, 0, 1, "positive ordered"),
        (1, 1, 2, 1, "positive ordered"),
        (1, 2, 1, 2, "positive ordered"),
    ],
)
def test_invalid_ranges_are_rejected_independently(
    start: int, end: int, start_column: int | None, end_column: int | None, error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        SourceAnnotation(
            "a.py", start, end, "bad", start_column=start_column, end_column=end_column
        )


def test_json_serialization_preserves_all_fields_and_optional_values() -> None:
    annotation = SourceAnnotation("a.py", 3, 3, "message", AnnotationLevel.NOTICE, "title", 1, 4)
    assert annotation.to_json() == {
        "path": "a.py",
        "startLine": 3,
        "endLine": 3,
        "message": "message",
        "level": "notice",
        "title": "title",
        "startColumn": 1,
        "endColumn": 4,
    }
    assert SourceAnnotation.from_json(annotation.to_json()) == annotation
    assert SourceAnnotation.from_json(
        {
            "path": "b.py",
            "startLine": 1,
            "endLine": 2,
            "message": "m",
            "level": "warning",
        }
    ) == SourceAnnotation("b.py", 1, 2, "m", AnnotationLevel.WARNING)
    with pytest.raises(ValueError, match="invalid"):
        SourceAnnotation.from_json(
            {
                "path": "b.py",
                "startLine": 1,
                "endLine": 1,
                "message": "m",
                "level": "invalid",
            }
        )


def test_grouping_distinguishes_every_location_property_and_deduplicates_messages() -> None:
    base = SourceAnnotation("a.py", 1, 1, "first", AnnotationLevel.WARNING, "title", 1, 2)

    distinct = [
        replace(base, path="b.py"),
        replace(base, start_line=2, end_line=2),
        replace(base, end_line=2, start_column=None, end_column=None),
        replace(base, level=AnnotationLevel.NOTICE),
        replace(base, title="other"),
        replace(base, start_column=2),
        replace(base, end_column=3),
    ]
    result = grouped_annotations([base, replace(base, message="second"), base, *distinct])
    assert result == (replace(base, message="first\nsecond"), *distinct)


def test_publishing_commands_and_notice_have_exact_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    annotation = SourceAnnotation("a%:,.py", 1, 2, "bad%\r\nnext", AnnotationLevel.NOTICE)
    publish_workflow_annotations(iter([annotation]), omitted_message="unused")
    assert capsys.readouterr().err == (
        "::notice file=a%25%3A%2C.py,line=1,endLine=2::bad%25%0D%0Anext\n"
    )
    stream = StringIO()
    publish_workflow_annotations(
        [annotation, annotation], omitted_message="more%\r\nfindings", stream=stream
    )
    assert stream.getvalue() == (
        "::notice file=a%25%3A%2C.py,line=1,endLine=2::bad%25%0D%0Anext\n"
        "::notice::more%25%0D%0Afindings\n"
    )
