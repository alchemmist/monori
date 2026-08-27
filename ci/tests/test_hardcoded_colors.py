from typing import cast

from monori.ci.quality_graph.checks.hardcoded_colors import (
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
        "web/package-lock.json",
        "ci/tests/fixtures/colors.ts",
    )

    assert all(not should_scan(path) for path in paths)


def test_native_result_contains_findings_annotations_and_controls() -> None:
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

    assert result["status"] == "failed"
    assert result["failureKind"] == "quality"
    findings = cast("list[dict[str, ResultValue]]", result["findings"])
    annotations = cast("list[dict[str, ResultValue]]", result["annotations"])
    controls = cast("list[dict[str, ResultValue]]", result["controls"])
    provenance = cast("dict[str, ResultValue]", result["provenance"])
    assert cast("str", findings[0]["id"]).startswith("color-")
    assert findings[0]["location"] == {
        "path": "example.css",
        "startLine": 1,
        "endLine": 1,
        "startColumn": 8,
        "endColumn": 14,
    }
    assert annotations[0]["location"] == findings[0]["location"]
    assert {control["kind"] for control in controls} == {"finding", "file", "node"}
    assert provenance["pullRequest"] == 7
    summary = summary_body([finding])
    assert "| File | Line | Literal | Format | Context | Status |" in summary
    assert "`/qg ignore hardcoded-colors`" in summary
    assert "`/qg ignore-file example.css`" in summary


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

    assert result["status"] == "passed"
    assert "failureKind" not in result
    assert "pullRequest" not in cast("dict[str, ResultValue]", result["provenance"])
