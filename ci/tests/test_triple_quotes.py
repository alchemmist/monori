from __future__ import annotations

from monori.ci.lib.triple_quotes import (
    DelimiterPosition,
    added_python_lines,
    scan_source,
)


def test_multiline_triple_quotes_require_delimiter_only_content_lines() -> None:
    source = 'valid = """\nbody\n"""\nbad_open = r"""body\n"""\nbad_close = f\'\'\'\nbody\'\'\'\n'

    findings = scan_source("example.py", source, frozenset(range(1, 10)))

    assert [(finding.line, finding.column, finding.delimiter) for finding in findings] == [
        (4, 13, '"""'),
        (7, 5, "'''"),
    ]


def test_one_line_triple_quoted_strings_require_ordinary_quotes() -> None:
    source = (
        "def example() -> str:\n"
        '    """A compact docstring."""\n'
        "    return '''compact literal'''\n"
    )

    findings = scan_source("example.py", source, frozenset({2, 3}))

    assert [(finding.line, finding.position) for finding in findings] == [
        (2, DelimiterPosition.INLINE),
        (3, DelimiterPosition.INLINE),
    ]
    assert findings[0].diagnostic.endswith("One-line triple-quoted string must use ordinary quotes")


def test_only_added_delimiter_lines_are_reported() -> None:
    source = 'value = """inline opening\nbody on an added line\ninline closing"""\n'

    assert scan_source("example.py", source, frozenset({2})) == ()
    assert [finding.line for finding in scan_source("example.py", source, frozenset({1, 3}))] == [
        1,
        3,
    ]


def test_patch_parser_returns_added_python_lines_only() -> None:
    patch = (
        "diff --git a/server/app/example.py b/server/app/example.py\n"
        "--- a/server/app/example.py\n"
        "+++ b/server/app/example.py\n"
        "@@ -2,0 +3,2 @@\n"
        '+value = """\n'
        "+body\n"
        "diff --git a/docs/example.md b/docs/example.md\n"
        "--- a/docs/example.md\n"
        "+++ b/docs/example.md\n"
        "@@ -1,0 +2 @@\n"
        '+"""\n'
    )

    assert added_python_lines(patch) == {"server/app/example.py": frozenset({3, 4})}


def test_patch_parser_tracks_context_deletions_markers_and_file_boundaries() -> None:
    patch = (
        "diff --git a/server/app/first.py b/server/app/first.py\n"
        "--- a/server/app/first.py\n"
        "+++ b/server/app/first.py\n"
        "@@ -4,2 +4,3 @@\n"
        " context\n"
        "-removed\n"
        "\\ No newline at end of file\n"
        "+first\n"
        " context\n"
        "diff --git a/server/app/incomplete.py b/server/app/incomplete.py\n"
        "@@ -0,0 +1 @@\n"
        "+ignored_without_path\n"
        "diff --git a/server/app/second.PY b/server/app/second.PY\n"
        "--- a/server/app/second.PY\n"
        "+++ b/server/app/second.PY\n"
        "@@ -0,0 +8 @@\n"
        "+second\n"
    )

    assert added_python_lines(patch) == {
        "server/app/first.py": frozenset({5}),
        "server/app/second.PY": frozenset({8}),
    }


def test_patch_parser_ignores_additions_before_a_hunk() -> None:
    patch = (
        "diff --git a/server/app/example.py b/server/app/example.py\n"
        "--- a/server/app/example.py\n"
        "+++ b/server/app/example.py\n"
        "+not_in_a_hunk\n"
    )

    assert added_python_lines(patch) == {}


def test_fstring_findings_preserve_all_locations_and_continue_scanning() -> None:
    source = (
        'first = f"""inline\n'
        "\n"
        'body"""\n'
        'compact = f"""one line"""\n'
        'second = f"""inline\n'
        "body\n"
        'closing"""\n'
    )

    findings = scan_source("nested/example.py", source, frozenset(range(1, 8)))

    assert [
        (finding.path, finding.line, finding.column, finding.position) for finding in findings
    ] == [
        ("nested/example.py", 1, 10, DelimiterPosition.OPENING),
        ("nested/example.py", 3, 5, DelimiterPosition.CLOSING),
        ("nested/example.py", 4, 12, DelimiterPosition.INLINE),
        ("nested/example.py", 5, 11, DelimiterPosition.OPENING),
        ("nested/example.py", 7, 8, DelimiterPosition.CLOSING),
    ]


def test_finding_diagnostic_names_the_required_layout() -> None:
    source = 'value = """inline\nbody\n"""\n'

    finding = scan_source("example.py", source, frozenset({1}))[0]

    assert finding.diagnostic == (
        'example.py:1:9: Triple-quoted multiline string must start with `"""` '
        "on a content-free line"
    )
