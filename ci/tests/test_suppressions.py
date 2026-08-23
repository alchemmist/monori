import pytest

from monori.ci.quality_graph.checks.suppressions import (
    SuppressionCheck,
    added_lines_from_patch,
    scan_file,
    summary_body,
)
from monori.ci.quality_graph.job_results import JobControl
from monori.ci.quality_graph.models import CheckContext, Verdict

NOQA = "# " + "no" + "qa"


class TestSuppressionGate:
    def test_check_class_collects_typed_result(self) -> None:
        result = SuppressionCheck().collect(
            CheckContext(
                files={"example.py": "value = 1  # " + "no" + "qa\n"},
                changed_lines={"example.py": frozenset({1})},
            )
        )

        assert result.verdict == Verdict.FAIL
        assert len(result.findings) == 1

    def test_finds_backend_and_frontend_suppressions_on_added_lines(self) -> None:
        source = f"""\
value = 1  {NOQA}: E501
const value = 1; // eslint-disable-next-line no-console
/* stylelint-disable color-no-invalid-hex */
"""

        findings = scan_file("example.ts", source, {1, 2, 3})

        assert [finding.line for finding in findings] == [1, 2, 3]

    def test_ignores_regular_code_and_existing_lines(self) -> None:
        source = f"""\
value = 1  {NOQA}: E501
value = 2
"""

        assert scan_file("example.py", source, {2}) == []

    def test_does_not_flag_detector_pattern_definition(self) -> None:
        source = 'SUPPRESSION_KEYS = r"(?:ignorePatterns|per-file-ignores)"\n'

        assert scan_file("ci/quality_graph/checks/suppressions.py", source, {1}) == []

    def test_finds_config_rule_disabled_on_added_line(self) -> None:
        findings = scan_file("web/eslint.config.mjs", '"no-console": "off",\n', {1})

        assert len(findings) == 1

    def test_does_not_treat_numeric_workflow_settings_as_suppressions(self) -> None:
        assert scan_file(".github/workflows/ci.yml", "fetch-depth: 0\n", {1}) == []

    def test_finds_entry_added_to_existing_toml_suppression_section(self) -> None:
        source = """\
[tool.ruff.lint.per-file-ignores]
"server/app.py" = ["E501"]
"""

        findings = scan_file("server/pyproject.toml", source, {2})

        assert len(findings) == 1
        assert findings[0].line == 2
        assert '"server/app.py" = ["E501"]' in findings[0].text

    def test_groups_multiline_toml_suppression_entry(self) -> None:
        source = """\
[tool.ruff.lint.per-file-ignores]
"ci/tests/**/*.py" = [
  "D102", "D103", "PLR2004",
  "D100", "S105"
]
"server/app/parser.py" = ["RUF001"]
"""

        findings = scan_file("pyproject.toml", source, {2, 3, 4, 5, 6, 7})

        assert [finding.line for finding in findings] == [2, 6]
        assert [finding.text for finding in findings] == [
            '"ci/tests/**/*.py" = [',
            '"server/app/parser.py" = ["RUF001"]',
        ]

    def test_added_line_inside_existing_multiline_toml_entry_is_reported_once(self) -> None:
        source = """\
[tool.ruff.lint.per-file-ignores]
"ci/tests/**/*.py" = [
  "D102",
  "D103",
]
"""

        findings = scan_file("pyproject.toml", source, {4})

        assert len(findings) == 1
        assert findings[0].line == 2
        assert findings[0].text == '"ci/tests/**/*.py" = ['

    def test_finds_single_quoted_toml_key(self) -> None:
        source = """\
[tool.ruff.lint.per-file-ignores]
'server/app/parser.py' = ["RUF001"]
"""

        findings = scan_file("pyproject.toml", source, {2})

        assert len(findings) == 1
        assert findings[0].text == "'server/app/parser.py' = [\"RUF001\"]"

    def test_compares_deserialized_toml_values_with_base(self) -> None:
        before = """\
[tool.ruff.lint.per-file-ignores]
"server/tests/**/*.py" = ["D101"]
"""
        after = """\
[tool.ruff.lint.per-file-ignores]
"server/tests/**/*.py" = ["D101", "D102"]
"server/migrations/**/*.py" = ["S101", "INP001"]
"server/app/workbook/parser.py" = ["RUF001"]
"server/app/connectors/tbank_playwright.py" = ["RUF001"]
"""

        findings = scan_file("pyproject.toml", after, {2, 3, 4, 5}, before)

        assert [finding.line for finding in findings] == [2, 3, 4, 5]

    def test_scopes_duplicate_toml_keys_by_suppression_section(self) -> None:
        source = """\
[tool.ruff.lint.per-file-ignores]
"server/app/parser.py" = ["E501"]

[tool.ruff.lint.extend-per-file-ignores]
"server/app/parser.py" = ["D100"]
"""

        findings = scan_file("pyproject.toml", source, {2, 5})

        assert [finding.line for finding in findings] == [2, 5]
        assert [finding.text for finding in findings] == [
            '"server/app/parser.py" = ["E501"]',
            '"server/app/parser.py" = ["D100"]',
        ]

    def test_finding_id_survives_line_shift_but_not_code_change(self) -> None:
        before = scan_file("example.py", f"value = 1  {NOQA}\n", {1})[0]
        after = scan_file("example.py", f"header = 0\nvalue = 1  {NOQA}\n", {2})[0]
        changed = scan_file("example.py", f"value = 2  {NOQA}\n", {1})[0]

        assert before.finding_id == after.finding_id
        assert before.finding_id != changed.finding_id

    def test_duplicate_suppressions_get_location_sensitive_ids(self) -> None:
        findings = scan_file(
            "example.py",
            f"value = 1  {NOQA}\nvalue = 1  {NOQA}\n",
            {1, 2},
        )

        assert len({finding.finding_id for finding in findings}) == 2

    def test_reads_added_lines_from_patch(self) -> None:
        patch = f"""\
@@ -1,2 +1,3 @@
 value = 1
+value = 2  {NOQA}
 value = 3
"""

        assert added_lines_from_patch(patch) == {2}

    def test_malformed_patch_and_toml_are_rejected(self) -> None:
        with pytest.raises(RuntimeError, match="Cannot parse diff hunk"):
            added_lines_from_patch("@@ malformed @@\n+value = 1")
        with pytest.raises(RuntimeError, match="Cannot parse TOML file"):
            scan_file("pyproject.toml", "[invalid\n", {1})

    def test_nested_toml_changes_are_detected(self) -> None:
        before = """\
[tool.ruff.lint.per-file-ignores]
"example.py" = { rules = ["E501"] }
"""
        after = """\
[tool.ruff.lint.per-file-ignores]
"example.py" = { rules = ["E501", "D100"] }
"""

        findings = scan_file("pyproject.toml", after, {2}, before)

        assert len(findings) == 1

    def test_summary_has_collapsed_admin_controls_without_report_marker(self) -> None:
        finding = scan_file("example.py", f"value = 1  {NOQA}\n", {1})[0]

        report = summary_body([finding], set(), "https://github.com/org/repo/pull/1")
        body = report.summary

        assert body.startswith("## ❌ Lint suppression gate\n")
        assert "| Status | FAIL |" in body
        assert "<details><summary>For repository administrators</summary>" in body
        assert "/qg ignore suppression-600043a9733a" in body
        assert "/qg ignore-file example.py" in body
        assert "[`example.py:1`](https://github.com/org/repo/pull/1/files#diff-" in body
        assert "<!-- monori-qg-control:" in body
        assert "<!-- monori-report:" not in body
        assert report.controls == (
            JobControl(
                "/qg ignore suppression-600043a9733a",
                "/qg remove-ignore suppression-600043a9733a",
            ),
            JobControl(
                "/qg ignore suppressions",
                "/qg remove-ignore suppression-600043a9733a",
            ),
            JobControl(
                "/qg ignore-file example.py",
                "/qg remove-ignore suppression-600043a9733a",
            ),
        )

    def test_summary_renders_an_approved_finding_as_passed(self) -> None:
        """Keep approved findings visible with their reversible control."""
        finding = scan_file("example.py", f"value = 1  {NOQA}\n", {1})[0]

        report = summary_body(
            [finding],
            {finding.finding_id},
            "https://github.com/org/repo/pull/1",
        )
        body = report.summary

        assert body.startswith("## ✅ Lint suppression gate\n")
        assert "| Status | PASS |\n| Findings | 1 |\n| Active | 0 |\n| Approved | 1 |" in body
        assert "- ✔ [`example.py:1`]" in body
        assert report.controls == (
            JobControl(
                "/qg ignore suppression-600043a9733a",
                "/qg remove-ignore suppression-600043a9733a",
                checked=True,
            ),
        )
