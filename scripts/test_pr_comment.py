import unittest

from scripts.pr_comment import JsonValue, comment_body, upsert_comment


class FakeGitHub:
    def __init__(self, comments: list[dict[str, JsonValue]]) -> None:
        self.items = comments
        self.calls: list[tuple[str, str, JsonValue]] = []

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        self.calls.append((method, path, payload))
        if path.startswith("/issues/1/comments"):
            return self.items
        return None


class PullRequestCommentTest(unittest.TestCase):
    def test_comment_body_has_a_stable_report_marker(self) -> None:
        self.assertEqual(
            comment_body("bundle-size", "## Bundle size\n"),
            "<!-- monori-report: bundle-size -->\n\n## Bundle size\n",
        )

    def test_updates_only_a_comment_owned_by_authenticated_user(self) -> None:
        github = FakeGitHub(
            [
                {
                    "id": 7,
                    "body": "<!-- monori-report: bundle-size -->\nold",
                    "user": {"login": "author"},
                },
                {
                    "id": 8,
                    "body": "<!-- monori-report: bundle-size -->\nold",
                    "user": {"login": "github-actions[bot]"},
                },
            ]
        )

        upsert_comment(github, 1, "bundle-size", "new")

        self.assertIn(
            (
                "PATCH",
                "/issues/comments/8",
                {"body": "<!-- monori-report: bundle-size -->\n\nnew\n"},
            ),
            github.calls,
        )
        self.assertNotIn(
            (
                "PATCH",
                "/issues/comments/7",
                {"body": "<!-- monori-report: bundle-size -->\n\nnew\n"},
            ),
            github.calls,
        )


if __name__ == "__main__":
    unittest.main()
