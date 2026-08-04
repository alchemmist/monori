"""Create or update one bot-owned report comment on a pull request."""

from __future__ import annotations

import argparse
import os
from itertools import count
from pathlib import Path
from typing import Protocol

from ci.lib.github import GITHUB_PAGE_SIZE, GitHub
from ci.lib.json import JsonValue, array_value, object_value


class GitHubAPI(Protocol):
    """Abstraction for GitHub API client used by comment helpers."""

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Execute one GitHub API request and return parsed JSON."""
        ...


def comments(github: GitHubAPI, number: int) -> list[dict[str, JsonValue]]:
    """Comments for this module."""
    result: list[dict[str, JsonValue]] = []
    for page in count(1):
        raw = github.request(
            "GET", f"/issues/{number}/comments?per_page={GITHUB_PAGE_SIZE}&page={page}"
        )
        items = array_value(raw, "pull request comments")
        result.extend(object_value(item, "pull request comment") for item in items)
        if len(items) < GITHUB_PAGE_SIZE:
            break
    return result


def comment_body(marker: str, body: str) -> str:
    """Comment body for this module."""
    return f"<!-- monori-report: {marker} -->\n\n{body.rstrip()}\n"


def upsert_comment(github: GitHubAPI, number: int, marker: str, body: str) -> None:
    """Upsert comment for this module."""
    rendered = comment_body(marker, body)
    configured_bot_login = os.environ.get("GITHUB_ACTIONS_BOT_LOGIN", "github-actions[bot]")
    workflow_bot_logins = {configured_bot_login, "monori-bot"}
    for comment in comments(github, number):
        comment_body_value = comment.get("body")
        author = object_value(comment.get("user", {}), "comment author").get("login")
        if (
            not isinstance(comment_body_value, str)
            or f"<!-- monori-report: {marker} -->" not in comment_body_value
            or author not in workflow_bot_logins
        ):
            continue
        comment_id = comment.get("id")
        if not isinstance(comment_id, int):
            message = "Pull request report comment has no numeric id"
            raise TypeError(message)
        github.request("PATCH", f"/issues/comments/{comment_id}", {"body": rendered})
        return
    github.request("POST", f"/issues/{number}/comments", {"body": rendered})


def main() -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--marker", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    args = parser.parse_args()
    upsert_comment(GitHub(), args.pr_number, args.marker, args.body_file.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
