import unittest

from scripts.suppression_gate import (
    Finding,
    JsonValue,
    added_lines_from_patch,
    parse_command,
    scan_file,
    summary_body,
    sync_approvals,
)


class FakeGitHub:
    def __init__(self, permission: str) -> None:
        self.permission = permission
        self.calls: list[tuple[str, str, JsonValue]] = []

    def paged(self, path: str) -> list[dict[str, JsonValue]]:
        self.calls.append(("paged", path, None))
        return [
            {"name": "monori-suppress-stale-finding"},
            {"name": "monori-suppress-finding-1"},
        ]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        self.calls.append((method, path, payload))
        if path.startswith("/collaborators/"):
            return {"permission": self.permission}
        return None

    def file_text(self, path: str, ref: str) -> str | None:
        return None

    def ensure_label(self, name: str) -> None:
        self.calls.append(("ensure_label", name, None))


class SuppressionGateTest(unittest.TestCase):
    def test_finds_backend_and_frontend_suppressions_on_added_lines(self) -> None:
        source = """\
value = 1  # noqa: E501
const value = 1; // eslint-disable-next-line no-console
/* stylelint-disable color-no-invalid-hex */
"""

        findings = scan_file("example.ts", source, {1, 2, 3})

        self.assertEqual([finding.line for finding in findings], [1, 2, 3])

    def test_ignores_regular_code_and_existing_lines(self) -> None:
        source = """\
value = 1  # noqa: E501
value = 2
"""

        self.assertEqual(scan_file("example.py", source, {2}), [])

    def test_finds_config_rule_disabled_on_added_line(self) -> None:
        findings = scan_file("web/eslint.config.mjs", '"no-console": "off",\n', {1})

        self.assertEqual(len(findings), 1)

    def test_does_not_treat_numeric_workflow_settings_as_suppressions(self) -> None:
        self.assertEqual(
            scan_file(".github/workflows/ci.yml", "fetch-depth: 0\n", {1}), []
        )

    def test_finds_entry_added_to_existing_toml_suppression_section(self) -> None:
        source = """\
[tool.ruff.lint.per-file-ignores]
"server/app.py" = ["E501"]
"""

        findings = scan_file("server/pyproject.toml", source, {2})

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 2)
        self.assertIn('"server/app.py" = ["E501"]', findings[0].text)

    def test_admin_can_approve_and_stale_labels_expire(self) -> None:
        github = FakeGitHub("admin")
        finding = Finding("example.py", 1, 0, "value = 1 # noqa", "finding-1")

        approved, admin = sync_approvals(
            github,
            334,
            {"body": ""},
            [finding],
            parse_command("/qg ignore suppression-finding-1"),
            "admin",
        )

        self.assertTrue(admin)
        self.assertEqual(approved, {"finding-1"})
        self.assertTrue(
            any(call[0] == "DELETE" and "stale" in call[1] for call in github.calls)
        )
        self.assertTrue(
            any(call[0] == "PATCH" and call[1] == "/pulls/334" for call in github.calls)
        )

    def test_non_admin_cannot_change_approval_state(self) -> None:
        github = FakeGitHub("write")
        finding = Finding("example.py", 1, 0, "value = 1 # noqa", "finding-1")

        approved, admin = sync_approvals(
            github, 334, {"body": ""}, [finding], parse_command("/qg ignore suppression"), "contributor"
        )

        self.assertFalse(admin)
        self.assertEqual(approved, {"finding-1"})
        self.assertFalse(any(call[0] == "POST" for call in github.calls))

    def test_finding_id_survives_line_shift_but_not_code_change(self) -> None:
        before = scan_file("example.py", "value = 1  # noqa\n", {1})[0]
        after = scan_file("example.py", "header = 0\nvalue = 1  # noqa\n", {2})[0]
        changed = scan_file("example.py", "value = 2  # noqa\n", {1})[0]

        self.assertEqual(before.finding_id, after.finding_id)
        self.assertNotEqual(before.finding_id, changed.finding_id)

    def test_duplicate_suppressions_get_location_sensitive_ids(self) -> None:
        findings = scan_file(
            "example.py",
            "value = 1  # noqa\nvalue = 1  # noqa\n",
            {1, 2},
        )

        self.assertEqual(len({finding.finding_id for finding in findings}), 2)

    def test_reads_added_lines_from_patch(self) -> None:
        patch = """\
@@ -1,2 +1,3 @@
 value = 1
+value = 2  # noqa
 value = 3
"""

        self.assertEqual(added_lines_from_patch(patch), {2})

    def test_commands_are_shared_between_gates(self) -> None:
        self.assertIsNotNone(parse_command("/qg ignore suppression-abc123"))
        self.assertIsNotNone(parse_command("/qg ignore-file server/app.py"))
        self.assertIsNotNone(parse_command("/qg ignore object-abc123,suppression-def456"))
        self.assertIsNotNone(parse_command("/qg ignore-file server/app.py,web/eslint.config.mjs"))
        self.assertIsNotNone(parse_command("/qg remove-ignore object-abc123,suppression-def456"))
        self.assertIsNone(parse_command("/qg ignore all"))
        self.assertIsNone(
            parse_command("/qg ignore suppression-abc123,,suppression-def456")
        )

    def test_summary_has_collapsed_admin_commands_and_no_comment_marker(self) -> None:
        finding = scan_file("example.py", "value = 1  # noqa\n", {1})[0]

        body = summary_body([finding], set())

        self.assertIn("❌ FAIL", body)
        self.assertIn("<details><summary>For repository administrators</summary>", body)
        self.assertIn("/qg ignore suppression-<finding-id>", body)
        self.assertNotIn("<!--", body)


if __name__ == "__main__":
    unittest.main()
