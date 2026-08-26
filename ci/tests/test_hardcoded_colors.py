from monori.ci.quality_graph.checks.hardcoded_colors import (
    HardcodedColorCheck,
    scan_file,
    should_scan,
    summary_body,
)
from monori.ci.quality_graph.models import CheckContext, Verdict


def test_detects_supported_color_syntax() -> None:
    source = """\
#abc #abcd #aabbcc #aabbccdd
rgb(1, 2, 3) rgba(10% 20% 30% / 40%)
hsl(120 50% 25%) hsla(120, 50%, 25%, .5) hwb(90 10% 20% / 30%)
lab(50% 20 30) lch(50% 40 120) oklab(.5 .1 .2) oklch(.5 .1 120)
color(display-p3 1 0 0) color(srgb 100% 0% 0% / 50%)
color: aliceblue; border-color: rebeccapurple;
"""

    findings = scan_file("web/src/colors.css", source, set(range(1, 7)))

    assert [finding.format for finding in findings] == [
        "HEX",
        "HEX",
        "HEX",
        "HEX",
        "RGB",
        "RGBA",
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
    source = """\
color: transparent; color: currentColor; color: inherit; color: initial;
color: unset; color: revert; color: color-mix(in srgb, var(--accent), var(--surface));
background: url(#abc); content: "issue #123"; href="#abc"; hash: abcdef1234567890;
const red = token; function blue() {}
"""

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


def test_check_annotation_and_summary_support_approvals() -> None:
    result = HardcodedColorCheck().collect(
        CheckContext(
            files={"example.css": "color: #ef5a17;\n"},
            changed_lines={"example.css": frozenset({1})},
        )
    )
    finding = result.findings[0]
    annotation = HardcodedColorCheck().source_annotation(finding)
    failed = summary_body([finding], set()).summary
    passed = summary_body([finding], {finding.finding_id}).summary

    assert result.verdict is Verdict.FAIL
    assert annotation.path == "example.css"
    assert annotation.start_line == annotation.end_line == 1
    assert annotation.start_column == 8
    assert annotation.end_column == 14
    assert "| File | Line | Literal | Format | Context | Status |" in failed
    assert "`/qg ignore hardcoded-colors`" in failed
    assert "`/qg ignore-file example.css`" in failed
    assert "## ✅ Hardcoded color gate" in passed
