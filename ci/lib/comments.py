"""Create or update one bot-owned report comment on a pull request."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from enum import StrEnum
from itertools import count
from pathlib import Path

from monori.ci.lib.github import GITHUB_PAGE_SIZE, GitHub, GitHubAPI
from monori.common import JsonValue, array_value, object_value

DEFAULT_BOT_LOGIN = "github-actions[bot]"
LEGACY_BOT_LOGIN = "monori-bot"
GITHUB_COMMENT_BODY_LIMIT = 65_536


class Reaction(StrEnum):
    """Represent GitHub reactions used by command-processing lifecycles."""

    ACKNOWLEDGED = "eyes"
    SUCCEEDED = "hooray"
    FAILED = "x"
    FORBIDDEN = "confused"


def workflow_bot_logins() -> set[str]:
    """Return logins allowed to own managed workflow comments and reactions."""
    configured = os.environ.get("GITHUB_ACTIONS_BOT_LOGIN", DEFAULT_BOT_LOGIN)
    return {configured, DEFAULT_BOT_LOGIN, LEGACY_BOT_LOGIN}


def issue_comments(github: GitHubAPI, number: int) -> list[dict[str, JsonValue]]:
    """Load every issue comment for a pull request."""
    result: list[dict[str, JsonValue]] = []
    for page in count(1):
        raw = github.request(
            "GET", f"/issues/{number}/comments?per_page={GITHUB_PAGE_SIZE}&page={page}"
        )
        items = array_value(raw, "pull request comments")
        result.extend(object_value(item, "pull request comment") for item in items)
        if len(items) < GITHUB_PAGE_SIZE:
            return result
    return result


def comment_body(marker: str, body: str) -> str:
    """Wrap report Markdown in its stable hidden marker."""
    return f"<!-- monori-report: {marker} -->\n\n{body.rstrip()}\n"


def managed_comment(github: GitHubAPI, number: int, marker: str) -> dict[str, JsonValue] | None:
    """Return the bot-owned pull-request comment carrying a report marker."""
    hidden_marker = f"<!-- monori-report: {marker} -->"
    bot_logins = workflow_bot_logins()
    for comment in issue_comments(github, number):
        body = comment.get("body")
        author = object_value(comment.get("user", {}), "comment author").get("login")
        if isinstance(body, str) and hidden_marker in body and author in bot_logins:
            return comment
    return None


def bounded_comment_body(body: str) -> str:
    """Fit a report within GitHub's comment limit and report the omitted size."""
    if len(body) <= GITHUB_COMMENT_BODY_LIMIT:
        return body
    omitted = len(body) - GITHUB_COMMENT_BODY_LIMIT
    while True:
        notice = f"\n\n_Report truncated; {omitted} characters omitted._\n"
        prefix_length = GITHUB_COMMENT_BODY_LIMIT - len(notice)
        updated_omitted = len(body) - prefix_length
        if updated_omitted == omitted:
            return body[:prefix_length] + notice
        omitted = updated_omitted


def upsert_comment(github: GitHubAPI, number: int, marker: str, body: str) -> None:
    """Create or update one bot-owned marked pull-request comment."""
    rendered = bounded_comment_body(comment_body(marker, body))
    existing = managed_comment(github, number, marker)
    if existing is not None:
        comment = existing
        comment_id = comment.get("id")
        if not isinstance(comment_id, int):
            message = "Pull request report comment has no numeric id"
            raise TypeError(message)
        github.request("PATCH", f"/issues/comments/{comment_id}", {"body": rendered})
        return
    github.request("POST", f"/issues/{number}/comments", {"body": rendered})


@dataclass(frozen=True)
class CommandReactionLifecycle:
    """Manage acknowledgement and final reactions for one command comment."""

    github: GitHubAPI
    comment_id: int

    def set(self, reaction: Reaction) -> None:
        """Replace the workflow bot's previous reaction with the requested state."""
        reactions = array_value(
            self.github.request("GET", f"/issues/comments/{self.comment_id}/reactions"),
            "comment reactions",
        )
        bot_logins = workflow_bot_logins()
        for item in reactions:
            current = object_value(item, "reaction")
            user = object_value(current.get("user", {}), "reaction user")
            reaction_id = current.get("id")
            if user.get("login") in bot_logins and isinstance(reaction_id, int):
                self.github.request(
                    "DELETE", f"/issues/comments/{self.comment_id}/reactions/{reaction_id}"
                )
        self.github.request(
            "POST",
            f"/issues/comments/{self.comment_id}/reactions",
            {"content": reaction.value},
        )

    def acknowledge(self) -> None:
        """Mark the command as noticed and awaiting processing."""
        self.set(Reaction.ACKNOWLEDGED)

    def succeed(self) -> None:
        """Mark the command as successfully processed."""
        self.set(Reaction.SUCCEEDED)

    def fail(self) -> None:
        """Mark the command as invalid or unsuccessfully processed."""
        self.set(Reaction.FAILED)

    def forbid(self) -> None:
        """Mark the command as rejected because the author lacks permission."""
        self.set(Reaction.FORBIDDEN)


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
