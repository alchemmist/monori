from __future__ import annotations

import re

import pytest

from monori.ci.lib.annotations import AnnotationLevel
from monori.ci.lib.findings import stable_finding_id
from monori.ci.lib.time_bombs import (
    EARLIEST_SECONDS,
    LATEST_SECONDS,
    diagnostic,
    parse_added_lines,
    scan_patch,
    timestamp_unit,
    validated_base,
)
from monori.ci.quality_graph.checks.time_bombs import TIME_BOMB_RESULT_ADAPTER
from monori.ci.quality_graph.job_results import JobStatus
from monori.ci.quality_graph.registry import WORKFLOW_JOB_BY_ID
from monori.ci.quality_graph.run_job import CommandResult

SECONDS = "17000" + "00000"
MILLISECONDS = SECONDS + "000"
MICROSECONDS = MILLISECONDS + "000"
NANOSECONDS = MICROSECONDS + "000"

PATCH = f"""diff --git a/server/app/example.py b/server/app/example.py
index 1111111..2222222 100644
--- a/server/app/example.py
+++ b/server/app/example.py
@@ -2,0 +3,2 @@
+created_at = {SECONDS}
+expires_at = {MILLISECONDS}
diff --git a/docs/example.md b/docs/example.md
index 3333333..4444444 100644
--- a/docs/example.md
+++ b/docs/example.md
@@ -1,0 +2 @@
+{NANOSECONDS}
"""


def test_parser_returns_only_added_source_lines() -> None:
    assert parse_added_lines(PATCH) == (
        ("server/app/example.py", 3, f"created_at = {SECONDS}"),
        ("server/app/example.py", 4, f"expires_at = {MILLISECONDS}"),
    )


def test_parser_tracks_context_deletions_markers_and_file_boundaries() -> None:
    patch = f"""diff --git a/server/app/first.py b/server/app/first.py
--- a/server/app/first.py
+++ b/server/app/first.py
+ignored_before_hunk = {SECONDS}
@@ -4,2 +4,3 @@
 context
-removed
\\ No newline at end of file
+first = {SECONDS}
 context
diff --git a/server/app/incomplete.py b/server/app/incomplete.py
@@ -0,0 +1 @@
+ignored_without_path = {MILLISECONDS}
diff --git a/server/app/second.py b/server/app/second.py
--- a/server/app/second.py
+++ b/server/app/second.py
@@ -0,0 +8 @@
+second = {MILLISECONDS}
"""

    assert parse_added_lines(patch) == (
        ("server/app/first.py", 5, f"first = {SECONDS}"),
        ("server/app/second.py", 8, f"second = {MILLISECONDS}"),
    )


def test_parser_treats_header_like_added_content_as_source() -> None:
    patch = f"""diff --git a/web/src/increment.ts b/web/src/increment.ts
--- a/web/src/increment.ts
+++ b/web/src/increment.ts
@@ -0,0 +1,2 @@
+++ b/{SECONDS}
+const later = {MILLISECONDS};
"""

    assert parse_added_lines(patch) == (
        ("web/src/increment.ts", 1, f"++ b/{SECONDS}"),
        ("web/src/increment.ts", 2, f"const later = {MILLISECONDS};"),
    )


def test_scanner_finds_seconds_milliseconds_microseconds_and_nanoseconds() -> None:
    patch = f"""diff --git a/web/src/time.test.ts b/web/src/time.test.ts
--- a/web/src/time.test.ts
+++ b/web/src/time.test.ts
@@ -0,0 +1,4 @@
+const seconds = {SECONDS};
+const milliseconds = {MILLISECONDS};
+const microseconds = {MICROSECONDS};
+const nanoseconds = {NANOSECONDS};
"""

    findings = scan_patch(patch)

    assert [(finding.line, finding.unit, finding.literal) for finding in findings] == [
        (1, "seconds", SECONDS),
        (2, "milliseconds", MILLISECONDS),
        (3, "microseconds", MICROSECONDS),
        (4, "nanoseconds", NANOSECONDS),
    ]


def test_scanner_accepts_numeric_separators_and_exact_range_boundaries() -> None:
    separated = f"{int(SECONDS):_}"
    patch = f"""diff --git a/server/app/time.py b/server/app/time.py
--- a/server/app/time.py
+++ b/server/app/time.py
@@ -0,0 +1 @@
+created_at = {separated}
"""

    assert scan_patch(patch)[0].literal == separated
    assert timestamp_unit(str(EARLIEST_SECONDS)) == "seconds"
    assert timestamp_unit(str(LATEST_SECONDS)) == "seconds"
    assert timestamp_unit(str(EARLIEST_SECONDS - 1)) is None
    assert timestamp_unit(str(LATEST_SECONDS + 1)) is None


def test_scanner_continues_after_an_implausible_number_on_the_same_line() -> None:
    patch = f"""diff --git a/server/app/time.py b/server/app/time.py
--- a/server/app/time.py
+++ b/server/app/time.py
@@ -0,0 +1 @@
+values = 9999999999999, {SECONDS}
"""

    finding = scan_patch(patch)[0]
    source = f"values = 9999999999999, {SECONDS}"
    start = source.index(SECONDS)

    assert finding.column == start + 1
    assert finding.finding_id == stable_finding_id(f"server/app/time.py:{source}:{SECONDS}:{start}")


def test_shell_and_node_script_findings_survive_shared_diagnostic_parsing() -> None:
    patch = f"""diff --git a/scripts/check.sh b/scripts/check.sh
--- a/scripts/check.sh
+++ b/scripts/check.sh
@@ -0,0 +1 @@
+deadline={SECONDS}
diff --git a/scripts/check.mjs b/scripts/check.mjs
--- a/scripts/check.mjs
+++ b/scripts/check.mjs
@@ -0,0 +1 @@
+const deadline = {MILLISECONDS};
"""
    output = "\n".join(diagnostic(finding) for finding in scan_patch(patch))

    result = TIME_BOMB_RESULT_ADAPTER.build(
        WORKFLOW_JOB_BY_ID["time-bombs"], CommandResult(0, output), ""
    )

    assert [annotation.path for annotation in result.annotations] == [
        "scripts/check.sh",
        "scripts/check.mjs",
    ]


def test_uppercase_source_suffix_survives_shared_diagnostic_parsing() -> None:
    patch = f"""diff --git a/scripts/check.MJS b/scripts/check.MJS
--- a/scripts/check.MJS
+++ b/scripts/check.MJS
@@ -0,0 +1 @@
+const deadline = {MILLISECONDS};
"""
    output = diagnostic(scan_patch(patch)[0])

    result = TIME_BOMB_RESULT_ADAPTER.build(
        WORKFLOW_JOB_BY_ID["time-bombs"], CommandResult(0, output), ""
    )

    assert result.annotations[0].path == "scripts/check.MJS"


def test_scanner_ignores_existing_lines_non_code_files_and_implausible_numbers() -> None:
    patch = f"""diff --git a/server/app/example.py b/server/app/example.py
--- a/server/app/example.py
+++ b/server/app/example.py
@@ -1,2 +1,3 @@
 old = {SECONDS}
-removed = {MILLISECONDS}
+version = 20260823
+future = 9999999999999
diff --git a/docs/example.md b/docs/example.md
--- a/docs/example.md
+++ b/docs/example.md
@@ -0,0 +1 @@
+timestamp = {SECONDS}
"""

    assert scan_patch(patch) == ()


def test_scanner_reports_each_literal_with_a_stable_warning_annotation() -> None:
    findings = scan_patch(PATCH)
    output = "\n".join(diagnostic(finding) for finding in findings)

    result = TIME_BOMB_RESULT_ADAPTER.build(
        WORKFLOW_JOB_BY_ID["time-bombs"], CommandResult(0, output), ""
    )

    assert result.status is JobStatus.WARNING
    assert result.metrics[0].value == "2"
    assert all(annotation.level is AnnotationLevel.WARNING for annotation in result.annotations)
    assert "server/app/example.py:3" in result.summary
    assert "Unix timestamp in seconds" in result.summary


def test_clean_patch_passes_without_annotations() -> None:
    result = TIME_BOMB_RESULT_ADAPTER.build(
        WORKFLOW_JOB_BY_ID["time-bombs"], CommandResult(0, ""), ""
    )

    assert result.status is JobStatus.PASSED
    assert result.annotations == ()


@pytest.mark.parametrize("value", ["", "--output=/tmp/result", "main;deploy", "$(deploy)"])
def test_base_ref_rejects_option_and_shell_syntax(value: str) -> None:
    with pytest.raises(ValueError, match=rf"^Invalid base ref: {re.escape(value)}$"):
        validated_base(value)


def test_base_ref_accepts_a_remote_branch() -> None:
    assert validated_base("origin/main") == "origin/main"
