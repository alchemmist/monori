"""Create or update one bot-owned report comment on a pull request."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from itertools import count
from pathlib import Path
from typing import Protocol, cast

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


def json_object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"Expected object for {context}")
    return value


def json_array(value: JsonValue, context: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError(f"Expected array for {context}")
    return value


class GitHub:
    def __init__(self) -> None:
        self.base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.repository = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        data = None if payload is None else json.dumps(payload).encode()
        api_path = path if path == "/user" else f"/repos/{self.repository}{path}"
        request = urllib.request.Request(
            f"{self.base}{api_path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return (
                    None
                    if response.status == 204
                    else cast(JsonValue, json.loads(response.read()))
                )
        except urllib.error.HTTPError as error:
            raise RuntimeError(
                f"GitHub API {method} {path} failed: HTTP {error.code}"
            ) from error


class GitHubAPI(Protocol):
    def request(
        self, method: str, path: str, payload: JsonValue = None
    ) -> JsonValue: ...


def comments(github: GitHubAPI, number: int) -> list[dict[str, JsonValue]]:
    result: list[dict[str, JsonValue]] = []
    for page in count(1):
        raw = github.request(
            "GET", f"/issues/{number}/comments?per_page=100&page={page}"
        )
        items = json_array(raw, "pull request comments")
        result.extend(json_object(item, "pull request comment") for item in items)
        if len(items) < 100:
            break
    return result


def comment_body(marker: str, body: str) -> str:
    return f"<!-- monori-report: {marker} -->\n\n{body.rstrip()}\n"


def upsert_comment(github: GitHubAPI, number: int, marker: str, body: str) -> None:
    rendered = comment_body(marker, body)
    workflow_bot_login = os.environ.get("GITHUB_ACTIONS_BOT_LOGIN", "github-actions[bot]")
    for comment in comments(github, number):
        comment_body_value = comment.get("body")
        author = json_object(comment.get("user", {}), "comment author").get("login")
        if (
            not isinstance(comment_body_value, str)
            or f"<!-- monori-report: {marker} -->" not in comment_body_value
            or author != workflow_bot_login
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
