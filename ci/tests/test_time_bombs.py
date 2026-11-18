import re

import pytest

from monori.ci.lib.findings import stable_finding_id
from monori.ci.lib.time_bombs import (
    EARLIEST_SECONDS,
    LATEST_SECONDS,
    diagnostic,
    main,
    parse_added_lines,
    scan_patch,
    timestamp_unit,
    validated_base,
)

SECONDS = "17000" + "00000"
MILLISECONDS = SECONDS + "000"
MICROSECONDS = MILLISECONDS + "000"
NANOSECONDS = MICROSECONDS + "000"


def patch_for(*lines: str, path: str = "server/app/time.py") -> str:
    added = "\n".join(f"+{line}" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n{added}\n"
    )


def test_parser_returns_only_added_source_lines() -> None:
    assert parse_added_lines(patch_for(f"created_at = {SECONDS}")) == (
        ("server/app/time.py", 1, f"created_at = {SECONDS}"),
    )


def test_scanner_finds_all_supported_timestamp_units() -> None:
    findings = scan_patch(
        patch_for(SECONDS, MILLISECONDS, MICROSECONDS, NANOSECONDS, path="web/src/time.ts")
    )
    assert [(finding.unit, finding.literal) for finding in findings] == [
        ("seconds", SECONDS),
        ("milliseconds", MILLISECONDS),
        ("microseconds", MICROSECONDS),
        ("nanoseconds", NANOSECONDS),
    ]


def test_timestamp_range_boundaries_and_numeric_separators() -> None:
    separated = f"{int(SECONDS):_}"
    assert scan_patch(patch_for(separated))[0].literal == separated
    assert timestamp_unit(str(EARLIEST_SECONDS)) == "seconds"
    assert timestamp_unit(str(LATEST_SECONDS)) == "seconds"
    assert timestamp_unit(str(EARLIEST_SECONDS - 1)) is None
    assert timestamp_unit(str(LATEST_SECONDS + 1)) is None


def test_scanner_continues_after_implausible_number() -> None:
    source = f"values = 9999999999999, {SECONDS}"
    finding = scan_patch(patch_for(source))[0]
    start = source.index(SECONDS)
    assert finding.column == start + 1
    assert finding.finding_id == stable_finding_id(f"server/app/time.py:{source}:{SECONDS}:{start}")


def test_scanner_ignores_non_code_files_and_implausible_values() -> None:
    assert scan_patch(patch_for(SECONDS, path="docs/time.md")) == ()
    assert scan_patch(patch_for("version = 20260823", "future = 9999999999999")) == ()


@pytest.mark.parametrize("value", ["", "--output=/tmp/result", "main;deploy", "$(deploy)"])
def test_base_ref_rejects_option_and_shell_syntax(value: str) -> None:
    with pytest.raises(ValueError, match=rf"^Invalid base ref: {re.escape(value)}$"):
        validated_base(value)


def test_base_ref_accepts_remote_branch() -> None:
    assert validated_base("origin/main") == "origin/main"


def test_diagnostic_and_main_publish_findings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    finding = scan_patch(patch_for(SECONDS))[0]
    assert "possible Unix timestamp in seconds" in diagnostic(finding)
    monkeypatch.setattr("monori.ci.lib.time_bombs.patch_for_base", lambda _base: patch_for(SECONDS))
    monkeypatch.setattr("sys.argv", ["time-bombs", "--base", "origin/main"])
    assert main() == 0
    assert "possible Unix timestamp in seconds" in capsys.readouterr().out
