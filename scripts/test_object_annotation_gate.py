import unittest

from object_annotation_gate import changed_lines, scan_file


class ObjectAnnotationGateTest(unittest.TestCase):
    def test_finds_direct_and_nested_annotations(self) -> None:
        source = """\
class Example:
    value: object

def function(value: list[object]) -> object | None:
    local: dict[str, object]
    return value
"""

        findings = scan_file("example.py", source, set(range(1, 20)))

        self.assertEqual([(finding.line, finding.annotation) for finding in findings], [
            (2, "object"),
            (4, "list[object]"),
            (4, "object | None"),
            (5, "dict[str, object]"),
        ])

    def test_ignores_calls_strings_and_comments(self) -> None:
        source = """\
value = object()
text = "object"
# object
"""

        self.assertEqual(scan_file("example.py", source, set(range(1, 10))), [])

    def test_reports_only_added_lines(self) -> None:
        before = "value: object\n"
        after = "value: object\nother: object\n"

        self.assertEqual(changed_lines(before, after), {2})
        findings = scan_file("example.py", after, changed_lines(before, after))
        self.assertEqual([(finding.line, finding.annotation) for finding in findings], [(2, "object")])


if __name__ == "__main__":
    unittest.main()
