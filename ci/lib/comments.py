"""Create or update one bot-owned report comment on a pull request."""

from __future__ import annotations

import argparse
from pathlib import Path

from ci.lib.github import GitHub
from ci.quality_graph.reporting import GitHubAPI, PullRequestReport
from ci.quality_graph.reporting import comment_body as render_comment_body


def comment_body(marker: str, body: str) -> str:
    """Wrap report Markdown in a stable marker for compatibility callers."""
    return render_comment_body(marker, body)


def upsert_comment(github: GitHubAPI, number: int, marker: str, body: str) -> None:
    """Publish through the shared pull-request report lifecycle."""
    PullRequestReport.registered(github, number, marker).publish(body)


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
