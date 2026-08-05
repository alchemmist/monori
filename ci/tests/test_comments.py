import unittest

from monori.ci.lib.comments import comment_body


class PullRequestCommentTest(unittest.TestCase):
    def test_comment_body_has_a_stable_report_marker(self) -> None:
        assert (
            comment_body("bundle-size", "## Bundle size\n")
            == "<!-- monori-report: bundle-size -->\n\n## Bundle size\n"
        )


if __name__ == "__main__":
    unittest.main()
