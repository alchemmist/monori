import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from monori.ci.quality_graph.checks.type_casts import (
    Finding,
    TypeCastCheck,
    repository_main,
    scan_file,
    summary_body,
)
from monori.ci.quality_graph.models import CheckContext, Verdict


class TestTypeCastGate:
    def test_check_collects_python_and_typescript_findings(self) -> None:
        result = TypeCastCheck().collect(
            CheckContext(
                files={
                    "example.py": "from typing import cast\nvalue = cast(str, raw)\n",
                    "example.ts": "const value = raw as string;\n",
                },
                changed_lines={
                    "example.py": frozenset({2}),
                    "example.ts": frozenset({1}),
                },
            )
        )

        assert result.verdict is Verdict.FAIL
        assert {finding.language for finding in result.findings} == {"python", "typescript"}

    def test_resolves_python_cast_imports_and_aliases(self) -> None:
        source = (
            "import typing\n"
            "import typing_extensions as typing_extensions_module\n"
            "from typing import cast\n"
            "from typing_extensions import cast as force_type\n"
            "\n"
            "one = typing.cast(str, raw)\n"
            "two = typing_extensions_module.cast(int, raw)\n"
            "three = cast(float, raw)\n"
            "four = force_type(bytes, raw)\n"
        )

        findings = scan_file("example.py", source, set(range(1, 20)))

        assert [(finding.line, finding.cast_form) for finding in findings] == [
            (6, "typing.cast"),
            (7, "typing_extensions_module.cast"),
            (8, "cast"),
            (9, "force_type"),
        ]

    def test_ignores_unresolved_python_cast_comments_and_strings(self) -> None:
        source = (
            "def cast(value):\n"
            "    return value\n"
            "\n"
            'text = "typing.cast(str, raw)"\n'
            "# from typing import cast\n"
            "value = cast(raw)\n"
        )

        assert scan_file("example.py", source, set(range(1, 20))) == []

    @pytest.mark.parametrize(
        "source",
        [
            "from typing import cast\ndef f(cast):\n    return cast(str, raw)\n",
            "from typing import cast\n"
            "def f():\n"
            "    cast = replacement\n"
            "    return cast(str, raw)\n",
            "import typing\ndef f(typing):\n    return typing.cast(str, raw)\n",
            "import typing\ntyping = replacement\nvalue = typing.cast(str, raw)\n",
        ],
    )
    def test_ignores_shadowed_python_cast_names(self, source: str) -> None:
        assert scan_file("example.py", source, set(range(1, 20))) == []

    def test_finds_typescript_assertion_forms_and_allows_as_const(self) -> None:
        source = (
            "const one = raw as Model;\n"
            "const two = raw as any;\n"
            "const three = raw as unknown as Model;\n"
            "const four = <Model>raw;\n"
            "const safe = {value: 1} as const;\n"
        )

        findings = scan_file("example.ts", source, set(range(1, 20)))

        assert [(finding.line, finding.cast_form) for finding in findings] == [
            (1, "as Model"),
            (2, "as any"),
            (3, "as unknown as Model"),
            (3, "as Model"),
            (4, "<Model>"),
        ]

    def test_ignores_typescript_comments_strings_import_aliases_and_tsx_angles(self) -> None:
        source = (
            "import {value as renamed} from './module';\n"
            'const text = "raw as Model";\n'
            "// raw as Model\n"
            "const view = <Component value={raw} />;\n"
        )

        assert scan_file("example.tsx", source, set(range(1, 20))) == []

    def test_finds_assertions_inside_template_interpolations(self) -> None:
        source = "const value = `prefix ${raw as string} suffix`;\n"

        findings = scan_file("example.ts", source, {1})

        assert [(finding.line, finding.cast_form) for finding in findings] == [(1, "as string")]

    @pytest.mark.parametrize(
        "source",
        [
            "const value = { as: raw };\n",
            "type Mapped<T> = { [K in keyof T as Name]: T[K] };\n",
            "import {\n  Foo\n  as\n  Bar\n} from './module';\n",
            "export {\n  Foo as\n  Bar\n};\n",
        ],
    )
    def test_ignores_non_assertion_typescript_as_syntax(self, source: str) -> None:
        assert scan_file("example.ts", source, set(range(1, 20))) == []

    def test_ignores_generated_files_and_headers(self) -> None:
        source = "const value = raw as Model;\n"

        assert scan_file("web/dist/example.ts", source, {1}) == []
        assert scan_file("example.ts", "// @generated\n" + source, {2}) == []

    def test_reports_only_selected_lines(self) -> None:
        source = "const old = raw as Old;\nconst added = raw as Added;\n"

        findings = scan_file("example.ts", source, {2})

        assert [(finding.line, finding.cast_form) for finding in findings] == [(2, "as Added")]

    def test_finding_ids_survive_line_shifts_and_change_with_the_cast(self) -> None:
        before = scan_file("example.ts", "const value = raw as Model;\n", {1})[0]
        shifted = scan_file("example.ts", "\nconst value = raw as Model;\n", {2})[0]
        changed = scan_file("example.ts", "const value = raw as Other;\n", {1})[0]

        assert before.finding_id == shifted.finding_id
        assert before.finding_id != changed.finding_id

    def test_duplicate_ids_do_not_depend_on_selected_line_subset(self) -> None:
        source = "const first = raw as Model;\nconst second = raw as Model;\n"
        both = scan_file("example.ts", source, {1, 2})
        second = scan_file("example.ts", source, {2})

        assert second[0].finding_id == both[1].finding_id

    def test_summary_exposes_location_language_form_id_and_suggestion(self) -> None:
        finding = Finding(
            "web/src/example.ts",
            3,
            12,
            "typescript",
            "as Model",
            "Narrow the value",
            "abc123",
        )

        report = summary_body([finding], set(), "https://github.com/org/repo/pull/1")

        assert report.summary.startswith("## ❌ Unsafe type cast gate\n")
        assert "web/src/example.ts:3" in report.summary
        assert "`typescript` · `as Model` · Narrow the value · `cast-abc123`" in report.summary
        assert "/qg ignore cast-abc123" in report.summary
        assert "/qg ignore-file web/src/example.ts" in report.summary

    def test_repository_mode_writes_machine_readable_findings(
        self,
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
        assert report[0] == {
            "cast_form": "cast",
            "column": 8,
            "finding_id": report[0]["finding_id"],
            "language": "python",
            "line": 2,
            "path": "example.py",
            "suggestion": "Narrow the type or validate at a boundary",
        }
