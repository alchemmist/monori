import os
import unittest
from typing import cast
from unittest import mock

from monori.ci.lib.comments import comment_body, upsert_comment
from monori.common import JsonValue


class FakeGitHub:
    def __init__(self, comments: list[dict[str, JsonValue]]) -> None:
        self.items = comments
        self.calls: list[tuple[str, str, JsonValue]] = []

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        self.calls.append((method, path, payload))
        if path.startswith("/issues/1/comments"):
            return cast("JsonValue", self.items)
        return None


class PullRequestCommentTest(unittest.TestCase):
    def test_comment_body_has_a_stable_report_marker(self) -> None:
        assert (
            comment_body("bundle-size", "## Bundle size\n")
            == "<!-- monori-report: bundle-size -->\n\n## Bundle size\n"
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

        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS_BOT_LOGIN": "github-actions[bot]"}):
            upsert_comment(github, 1, "bundle-size", "new")

        assert (
            "PATCH",
            "/issues/comments/8",
            {"body": "<!-- monori-report: bundle-size -->\n\nnew\n"},
        ) in github.calls
        assert (
            "PATCH",
            "/issues/comments/7",
            {"body": "<!-- monori-report: bundle-size -->\n\nnew\n"},
        ) not in github.calls

    def test_updates_a_legacy_bot_comment(self) -> None:
        github = FakeGitHub(
            [
                {
                    "id": 8,
                    "body": "<!-- monori-report: bundle-size -->\nold",
                    "user": {"login": "monori-bot"},
                }
            ]
        )

        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS_BOT_LOGIN": "custom-bot"}):
            upsert_comment(github, 1, "bundle-size", "new")

        assert ("PATCH", "/issues/comments/8", mock.ANY) in github.calls


if __name__ == "__main__":
    unittest.main()
