from typing import cast

import pytest

from monori.ci.quality_graph.checks.hardcoded_colors import (
    Finding,
    ResultValue,
    result_value,
    scan_file,
    should_scan,
    summary_body,
)


def test_detects_supported_color_syntax() -> None:
    source = (
        "#abc #abcd #aabbcc #aabbccdd\n"
        "rgb(1, 2, 3) rgba(10% 20% 30% / 40%) rgb(calc(128) 0 0)\n"
        "hsl(120 50% 25%) hsla(120, 50%, 25%, .5) hwb(90 10% 20% / 30%)\n"
        "lab(50% 20 30) lch(50% 40 120) oklab(.5 .1 .2) oklch(.5 .1 120)\n"
        "color(display-p3 1 0 0) color(srgb 100% 0% 0% / 50%)\n"
        "color: aliceblue; border-color: rebeccapurple;\n"
    )

    findings = scan_file("web/src/colors.css", source, set(range(1, 7)))

    assert [finding.format for finding in findings] == [
        "HEX",
        "HEX",
        "HEX",
        "HEX",
        "RGB",
        "RGBA",
        "RGB",
        "HSL",
        "HSLA",
        "HWB",
        "LAB",
        "LCH",
        "OKLAB",
        "OKLCH",
        "COLOR",
        "COLOR",
        "NAMED",
        "NAMED",
    ]


def test_detects_literals_in_supported_source_contexts() -> None:
    cases = {
        "example.svg": '<path fill="#fff" stroke="red"/>',
        "example.html": '<div style="color: rgb(1 2 3)">',
        "example.ts": 'const color = "#112233";',
        "example.tsx": '<div style={{ color: "tomato" }} />',
        "example.json": '{"color": "hsl(0 100% 50%)"}',
        "example.css": "--new-palette-entry: #ef5a17;",
    }

    assert all(scan_file(path, source, {1}) for path, source in cases.items())


def test_detects_nested_calculations_in_color_functions() -> None:
    findings = scan_file("example.css", "color: rgb(calc(128) 0 0);\n", {1})

    assert [(finding.literal, finding.format) for finding in findings] == [
        ("rgb(calc(128) 0 0)", "RGB")
    ]


def test_detects_multiline_functions_when_added_lines_overlap() -> None:
    source = "color: rgb(\n  1 2 3\n);\n"

    findings = scan_file("example.css", source, {2})

    assert [(finding.line, finding.literal, finding.format) for finding in findings] == [
        (2, "rgb(\n  1 2 3\n)", "RGB")
    ]


def test_detects_named_colors_in_shorthand_declarations() -> None:
    findings = scan_file("example.css", "border: 1px solid red;\n", {1})

    assert [(finding.literal, finding.format) for finding in findings] == [("red", "NAMED")]


def test_scans_added_lines_only_and_finds_multiple_literals() -> None:
    findings = scan_file("example.css", "color: red;\nbox-shadow: 0 0 #fff, 0 0 rgb(1 2 3);\n", {2})

    assert [finding.literal for finding in findings] == ["#fff", "rgb(1 2 3)"]


def test_location_sensitive_ids_distinguish_duplicates() -> None:
    findings = scan_file("example.css", "color: #fff;\ncolor: #fff;\n", {1, 2})
    repeated = scan_file("example.css", "color: #fff;\ncolor: #fff;\n", {1, 2})

    assert len({finding.finding_id for finding in findings}) == 2
    assert [finding.finding_id for finding in findings] == [
        finding.finding_id for finding in repeated
    ]


def test_excludes_semantic_keywords_variable_only_functions_and_false_positives() -> None:
    source = (
        "color: transparent; color: currentColor; color: inherit; color: initial;\n"
        "color: unset; color: revert; "
        "color: color-mix(in srgb, var(--accent), var(--surface));\n"
        'background: url(#abc); content: "issue #123"; '
        'href="#abc"; hash: abcdef1234567890;\n'
        "const red = token; function blue() {}\n"
    )

    assert scan_file("example.ts", source, {1, 2, 3, 4}) == []


def test_excludes_generated_vendor_minified_lockfiles_and_fixtures() -> None:
    paths = (
        "vendor/colors.css",
        "web/dist/app.css",
        "web/build/app.js",
        "web/app.min.css",
        "web/app.min.js",
        "web/package-lock.json",
        "ci/tests/fixtures/colors.ts",
    )

    assert all(not should_scan(path) for path in paths)
    assert should_scan("web/src/app.css")
    assert should_scan("web/src/app.tsx")


@pytest.mark.parametrize(
    ("path", "source", "expected"),
    [
        ("example.ts", 'const color = "red";', ["red"]),
        ("example.ts", 'const color =   "red"   ;', ["red"]),
        ("example.ts", "const color = 'blue';", ["blue"]),
        ("example.ts", "const color = `green`;", ["green"]),
        ("example.css", "border: 1px solid red;", ["red"]),
        ("example.ts", "const red = token;", []),
        ("example.ts", "const color: Token = red;", []),
        ("example.html", '<div style="color: red">', ["red"]),
        ("example.css", "color: var(--red);", []),
        ("example.css", "content: red; const blue = token;", ["red"]),
        ("example.css", "color: red; border: blue; const green = token;", ["red", "blue"]),
        ("example.css", "a: b = color: red", ["red"]),
        ("example.css", "a=x: y=red", []),
    ],
)
def test_named_color_literal_boundaries(path: str, source: str, expected: list[str]) -> None:
    assert [finding.literal for finding in scan_file(path, source, {1})] == expected


@pytest.mark.parametrize(
    "source",
    [
        "color: rgb(1 2 3;",
        "color: rgb(var(--red) var(--green) var(--blue));",
    ],
)
def test_ignores_incomplete_or_variable_only_color_functions(source: str) -> None:
    assert scan_file("example.css", source, {1}) == []


def test_ignores_numbered_variable_only_color_functions() -> None:
    source = "rgb(var(--red-500) var(--green-500) var(--blue-500))"

    assert scan_file("example.css", source, {1}) == []


def test_balanced_function_parser_ignores_parentheses_inside_quotes() -> None:
    findings = scan_file("example.css", 'color: rgb(")" 1 2 3);\n', {1})

    assert findings == [
        Finding(
            "example.css",
            1,
            7,
            'rgb(")" 1 2 3)',
            "RGB",
            'rgb(")" 1 2 3)',
            "color-7eb545bda61f",
        )
    ]


@pytest.mark.parametrize(
    "source",
    [
        "color: rgb(')' 1 2 3);\n",
        'color: rgb("escaped \\" )" 1 2 3);\n',
    ],
)
def test_balanced_function_parser_tracks_quote_boundaries(source: str) -> None:
    findings = scan_file("example.css", source, {1})

    assert len(findings) == 1
    assert findings[0].literal.endswith("1 2 3)")


def test_native_result_contains_semantic_findings_and_annotations() -> None:
    finding = scan_file("example.css", "color: #ef5a17;\n", {1})[0]
    result = result_value(
        [finding],
        {
            "GITHUB_REPOSITORY": "org/repo",
            "QG_HEAD_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
            "QG_PULL_REQUEST": "7",
        },
        "b" * 64,
    )

    location: dict[str, ResultValue] = {
        "path": "example.css",
        "startLine": 1,
        "endLine": 1,
        "startColumn": 8,
        "endColumn": 14,
    }
    summary = (
        "| File | Line | Literal | Format | Context | Status |\n"
        "| --- | ---: | --- | --- | --- | --- |\n"
        "| `example.css` | 1 | `#ef5a17` | HEX | `color: #ef5a17;` | active |"
    )
    assert result == {
        "schemaVersion": 0,
        "nodeId": "hardcoded-colors",
        "title": "Hardcoded color gate",
        "status": "failed",
        "failureKind": "quality",
        "summary": summary,
        "metrics": [
            {"label": "Status", "value": "FAIL"},
            {"label": "Findings", "value": "1"},
        ],
        "findings": [
            {
                "id": "color-09ab56808930",
                "severity": "error",
                "message": "Hardcoded HEX color: #ef5a17",
                "ruleId": "hardcoded-color",
                "fingerprint": "color-09ab56808930",
                "location": location,
                "group": "HEX",
            }
        ],
        "annotations": [
            {
                "level": "error",
                "message": "Hardcoded HEX color: #ef5a17",
                "title": "Hardcoded color gate",
                "location": location,
            }
        ],
        "diagnostics": [],
        "controls": [],
        "notes": ["Color finding IDs are stable and location-sensitive."],
        "provenance": {
            "repository": "org/repo",
            "headSha": "a" * 40,
            "workflowRunId": 123,
            "runAttempt": 2,
            "graphDigest": "b" * 64,
            "pullRequest": 7,
        },
    }


def test_passing_native_result_has_no_failure_kind() -> None:
    result = result_value(
        [],
        {
            "GITHUB_REPOSITORY": "org/repo",
            "QG_HEAD_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "QG_PULL_REQUEST": "0",
        },
        "b" * 64,
    )

    assert result == {
        "schemaVersion": 0,
        "nodeId": "hardcoded-colors",
        "title": "Hardcoded color gate",
        "status": "passed",
        "summary": "No hardcoded colors found.",
        "metrics": [
            {"label": "Status", "value": "PASS"},
            {"label": "Findings", "value": "0"},
        ],
        "findings": [],
        "annotations": [],
        "diagnostics": [],
        "controls": [],
        "notes": ["Color finding IDs are stable and location-sensitive."],
        "provenance": {
            "repository": "org/repo",
            "headSha": "a" * 40,
            "workflowRunId": 123,
            "runAttempt": 1,
            "graphDigest": "b" * 64,
        },
    }


def test_multiline_finding_has_exact_location_context_and_id() -> None:
    findings = scan_file("example.css", "color: rgb(\n  1 2 3\n);\n", {2})

    assert findings == [
        Finding(
            "example.css",
            2,
            0,
            "rgb(\n  1 2 3\n)",
            "RGB",
            "rgb( 1 2 3 )",
            "color-16ec146e7967",
        )
    ]


def test_summary_escapes_table_cells_without_framework_controls() -> None:
    findings = scan_file("web/a|b.css", "color: red; /* `context` */\n", {1})

    summary = summary_body(findings)

    assert "`web/a\\|b.css`" in summary
    assert "`color: red; /* \\`context\\` */`" in summary
    assert "/qg" not in summary


def test_summary_keeps_domain_rows_only() -> None:
    first = scan_file("z.css", "color: red;\n", {1})[0]
    second = scan_file("a.css", "color: blue;\n", {1})[0]

    summary = summary_body([first, second])

    assert "`z.css`" in summary
    assert "`a.css`" in summary
    assert "/qg" not in summary


def test_summary_flattens_multiline_literals_and_truncates_context() -> None:
    finding = Finding(
        "example.css",
        2,
        0,
        "rgb(\n1 2 3\n)",
        "RGB",
        "x" * 201,
        "color-example",
    )

    summary = summary_body([finding])

    assert "`rgb( 1 2 3 )`" in summary
    assert f"`{'x' * 200}`" in summary
    assert "x" * 201 not in summary
