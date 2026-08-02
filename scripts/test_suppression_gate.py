import unittest

from scripts.suppression_gate import (
    added_lines_from_patch,
    parse_command,
    scan_file,
    summary_body,
)


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

    def test_reads_added_lines_from_patch(self) -> None:
        patch = """\
@@ -1,2 +1,3 @@
 value = 1
+value = 2  # noqa
 value = 3
"""

        self.assertEqual(added_lines_from_patch(patch), {2})

    def test_commands_are_exact(self) -> None:
        self.assertEqual(
            parse_command("/ignore-suppression abc123"),
            ("ignore-suppression", "abc123"),
        )
        self.assertEqual(
            parse_command("/ignore-file server/app.py"),
            ("ignore-file", "server/app.py"),
        )
        self.assertEqual(parse_command("/ignore-all"), ("ignore-all", None))
        self.assertEqual(parse_command("/remove-ignore abc123"), ("remove-ignore", "abc123"))
        self.assertIsNone(parse_command("/ignore-all extra"))

    def test_summary_has_collapsed_admin_commands_and_no_comment_marker(self) -> None:
        finding = scan_file("example.py", "value = 1  # noqa\n", {1})[0]

        body = summary_body([finding], set())

        self.assertIn("❌ FAIL", body)
        self.assertIn("<details><summary>For repository administrators</summary>", body)
        self.assertIn("/ignore-suppression", body)
        self.assertNotIn("<!--", body)


if __name__ == "__main__":
    unittest.main()
