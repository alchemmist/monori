"""Create or update one bot-owned report comment on a pull request."""

from __future__ import annotations

import argparse
import os
from itertools import count
from pathlib import Path
from typing import Protocol

from ci.lib.github import GitHub
from ci.lib.json import JsonValue, array_value, object_value


class GitHubAPI(Protocol):
    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue: ...


def comments(github: GitHubAPI, number: int) -> list[dict[str, JsonValue]]:
    result: list[dict[str, JsonValue]] = []
    for page in count(1):
        raw = github.request("GET", f"/issues/{number}/comments?per_page=100&page={page}")
        items = array_value(raw, "pull request comments")
        result.extend(object_value(item, "pull request comment") for item in items)
        if len(items) < 100:
            break
    return result


def comment_body(marker: str, body: str) -> str:
    return f"<!-- monori-report: {marker} -->\n\n{body.rstrip()}\n"


def upsert_comment(github: GitHubAPI, number: int, marker: str, body: str) -> None:
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
            raise TypeError("Pull request report comment has no numeric id")
        github.request("PATCH", f"/issues/comments/{comment_id}", {"body": rendered})
        return
    github.request("POST", f"/issues/{number}/comments", {"body": rendered})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marker", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    args = parser.parse_args()
    upsert_comment(GitHub(), args.pr_number, args.marker, args.body_file.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
