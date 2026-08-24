import json
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest

from monori.ci.quality_graph.checks.type_casts import (
    Finding,
    TypeCastCheck,
    repository_main,
    scan_file,
    scan_pull_request,
    summary_body,
)
from monori.ci.quality_graph.models import CheckContext, Verdict
from monori.common import JsonValue


class TestTypeCastGate:
    def test_scanner_is_excluded_from_expression_mutation(self) -> None:
        configuration = tomllib.loads(Path("pyproject.toml").read_text())

        assert configuration["tool"]["mutmut"]["do_not_mutate"] == [
            "*ci/quality_graph/checks/type_casts.py"
        ]

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

    def test_ignores_invalid_python_and_unsupported_files(self) -> None:
        assert scan_file("broken.py", "value = (", {1}) == []
        assert scan_file("example.txt", "raw as Model", {1}) == []

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

    def test_finds_assertions_inside_tsx_expressions(self) -> None:
        source = "const view = <Component value={raw as Model} />;\n"

        findings = scan_file("example.tsx", source, {1})

        assert [(finding.line, finding.cast_form) for finding in findings] == [(1, "as Model")]

    def test_finds_assertions_inside_template_interpolations(self) -> None:
        source = "const value = `prefix ${raw as string} suffix`;\n"

        findings = scan_file("example.ts", source, {1})

        assert [(finding.line, finding.cast_form) for finding in findings] == [(1, "as string")]

    def test_finds_assertions_after_dynamic_imports(self) -> None:
        source = 'const module = (await import("./module")) as Module;\n'

        findings = scan_file("example.ts", source, {1})

        assert [(finding.line, finding.cast_form) for finding in findings] == [(1, "as Module")]

    def test_template_scanner_handles_escapes_quotes_and_nested_braces(self) -> None:
        source = (
            "const escaped = `\\` ${raw as Model}`;\n"
            "const quoted = `${call('}', {value: raw as Model})}`;\n"
            "const unfinished = `${raw as Model`;\n"
        )

        findings = scan_file("example.ts", source, {1, 2, 3})

        assert [finding.line for finding in findings] == [1, 2, 3]

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

    def test_handles_nested_and_multiline_assertion_types(self) -> None:
        source = (
            "const nested = raw as Map<string, Array<Model>>;\n"
            "const parenthesized = raw as (Model | Other);\n"
            "const multiline = raw as\nModel;\n"
        )

        findings = scan_file("example.ts", source, {1, 2, 3})

        assert [finding.line for finding in findings] == [1, 2, 3]

    def test_ignores_angle_syntax_that_is_not_an_assertion(self) -> None:
        source = (
            "const generic = <Schema extends Base>(value: Schema) => value;\n"
            "const incomplete = <Model;\n"
            "const empty = <>value;\n"
            "const comparison = left < Model > value;\n"
        )

        assert scan_file("example.ts", source, set(range(1, 10))) == []

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

    def test_check_builds_precise_source_annotation(self) -> None:
        finding = scan_file("example.ts", "const value = raw as Model;\n", {1})[0]

        annotation = TypeCastCheck().source_annotation(finding)

        assert (annotation.path, annotation.start_line, annotation.start_column) == (
            "example.ts",
            1,
            19,
        )
        assert "cast-" in annotation.message

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

    def test_repository_mode_can_print_a_non_blocking_inventory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (tmp_path / "example.ts").write_text("const value = raw as Model;\n")
        monkeypatch.chdir(tmp_path)

        class Index:
            def __iter__(self) -> Iterator[bytes]:
                return iter((b"README.md", b"example.ts"))

        class Repository:
            def open_index(self) -> Index:
                return Index()

        monkeypatch.setattr(
            "monori.ci.quality_graph.checks.type_casts.Repo.discover",
            lambda _root: Repository(),
        )

        assert repository_main([]) == 0
        assert json.loads(capsys.readouterr().out)[0]["cast_form"] == "as Model"

    def test_pull_request_scan_uses_patches_and_merge_base_fallback(self) -> None:
        class GitHub:
            def paged(self, path: str) -> list[dict[str, JsonValue]]:
                assert path == "/pulls/7/files"
                return [
                    {
                        "filename": "added.ts",
                        "status": "added",
                        "patch": "@@ -0,0 +1 @@\n+const value = raw as Model;",
                    },
                    {
                        "filename": "renamed.py",
                        "previous_filename": "before.py",
                        "status": "renamed",
                    },
                    {"filename": "removed.py", "status": "removed"},
                    {"filename": "README.md", "status": "modified"},
                ]

            def request(self, method: str, path: str, _payload: JsonValue = None) -> JsonValue:
                assert (method, path) == ("GET", "/compare/base...head")
                return {"merge_base_commit": {"sha": "merge-base"}}

            def file_text(self, path: str, revision: str) -> str | None:
                files = {
                    ("added.ts", "head"): "const value = raw as Model;\n",
                    ("renamed.py", "head"): "from typing import cast\nvalue = cast(str, raw)\n",
                    ("before.py", "merge-base"): "from typing import cast\n",
                }
                return files.get((path, revision))

        pull: dict[str, JsonValue] = {
            "number": 7,
            "head": {"sha": "head"},
            "base": {"sha": "base"},
        }

        findings = scan_pull_request(GitHub(), pull)

        assert [(finding.path, finding.line) for finding in findings] == [
            ("added.ts", 1),
            ("renamed.py", 2),
        ]

    def test_pull_request_scan_rejects_an_unreadable_changed_file(self) -> None:
        class GitHub:
            def paged(self, _path: str) -> list[dict[str, JsonValue]]:
                return [{"filename": "missing.py", "status": "modified"}]

            def request(self, _method: str, _path: str, _payload: JsonValue = None) -> JsonValue:
                return {"merge_base_commit": {"sha": "merge-base"}}

            def file_text(self, _path: str, _revision: str) -> None:
                return None

        pull: dict[str, JsonValue] = {
            "number": 7,
            "head": {"sha": "head"},
            "base": {"sha": "base"},
        }

        with pytest.raises(RuntimeError, match=r"Cannot read changed source file missing\.py"):
            scan_pull_request(GitHub(), pull)
