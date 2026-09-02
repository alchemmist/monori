import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from monori.ci.quality_graph.checks.type_casts import repository_main, scan_file


def test_scans_python_and_typescript_casts() -> None:
    python = scan_file(
        "example.py",
        "import typing\n"
        "from typing import cast as force\n"
        "a = typing.cast(str, raw)\n"
        "b = force(int, raw)\n",
        {3, 4},
    )
    typescript = scan_file(
        "example.ts",
        "const one = raw as Model;\nconst two = <Other>raw;\nconst safe = raw as const;\n",
        {1, 2, 3},
    )

    assert [finding.cast_form for finding in python] == ["typing.cast", "force"]
    assert [finding.cast_form for finding in typescript] == ["as Model", "<Other>"]


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("example.py", "def cast(value):\n    return value\nvalue = cast(raw)\n"),
        ("example.ts", "import { value as renamed } from './module';\n"),
        ("example.tsx", "const view = <Component value={raw} />;\n"),
        ("web/dist/example.ts", "const value = raw as Model;\n"),
    ],
)
def test_ignores_non_cast_and_generated_sources(path: str, source: str) -> None:
    assert scan_file(path, source, set(range(1, 20))) == []


def test_finds_assertions_in_typescript_expressions() -> None:
    source = (
        "const view = <Component value={raw as Model} />;\nconst template = `${raw as string}`;\n"
    )

    findings = scan_file("example.tsx", source, {1, 2, 3})

    assert [(finding.line, finding.cast_form) for finding in findings] == [
        (1, "as Model"),
        (2, "as string"),
    ]
    imported = scan_file(
        "example.ts",
        "const imported = (await import('./module')) as Module;\n",
        {1},
    )
    assert imported[0].cast_form == "as Module"


def test_finding_ids_are_stable_across_line_shifts() -> None:
    before = scan_file("example.ts", "const value = raw as Model;\n", {1})[0]
    shifted = scan_file("example.ts", "\nconst value = raw as Model;\n", {2})[0]
    changed = scan_file("example.ts", "const value = raw as Other;\n", {1})[0]

    assert before.finding_id == shifted.finding_id
    assert before.finding_id != changed.finding_id


def test_repository_mode_writes_machine_readable_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "example.py").write_text("from typing import cast\nvalue = cast(str, raw)\n")
    output = tmp_path / "report.json"
    monkeypatch.chdir(tmp_path)

    class Index:
        def __iter__(self) -> Iterator[bytes]:
            return iter((b"example.py",))

    class Repository:
        def open_index(self) -> Index:
            return Index()

    monkeypatch.setattr(
        "monori.ci.quality_graph.checks.type_casts.Repo.discover",
        lambda _root: Repository(),
    )

    assert repository_main(["--output", str(output), "--fail"]) == 1
    report = json.loads(output.read_text())
    assert report[0]["cast_form"] == "cast"
    assert report[0]["path"] == "example.py"
