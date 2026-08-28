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
