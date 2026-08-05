"""Tests for shared Quality Graph report and reaction lifecycles."""

import re
from typing import cast

from monori.ci.lib.comments import (
    GITHUB_COMMENT_BODY_LIMIT,
    CommandReactionLifecycle,
    bounded_comment_body,
)
from monori.ci.quality_graph.reporting import (
    PullRequestReport,
    ReportFinding,
    ReportMetric,
    ReportModel,
    ReportStatus,
    admin_commands,
    finding_location,
    render_report,
)
from monori.common import JsonValue


class FakeGitHub:
    """Record report lifecycle API calls and return configured comments."""

    def __init__(self, comments: list[dict[str, JsonValue]] | None = None) -> None:
        """Store comments returned by list operations."""
        self.comments = comments or []
        self.calls: list[tuple[str, str, JsonValue]] = []

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Record an API request and return fixture data for list endpoints."""
        self.calls.append((method, path, payload))
        if "/comments?" in path:
            return cast("JsonValue", self.comments)
        if path.endswith("/reactions") and method == "GET":
            return cast(
                "JsonValue",
                [
                    {
                        "id": 9,
                        "content": "eyes",
                        "user": {"login": "github-actions[bot]"},
                    }
                ],
            )
        return None


def test_renderer_owns_status_heading_findings_and_admin_commands() -> None:
    """Render the complete common report frame from typed gate data."""
    body = render_report(
        ReportModel(
            "suppression",
            ReportStatus.FAIL,
            metrics=(ReportMetric("Active", "1"),),
            findings=(
                ReportFinding(
                    "`example-1`",
                    location=finding_location(
                        "https://github.com/org/repo/pull/1", "example.py", 1
                    ),
                ),
            ),
            admin=admin_commands("example", ["example-1"], [], ["example.py"]),
        )
    )

    assert body.startswith("## ❌ Lint suppression gate\n")
    assert "| Active | 1 |" in body
    assert "<details><summary>Findings (1)</summary>" in body
    assert "[`example.py:1`](https://github.com/org/repo/pull/1/files#diff-" in body
    assert "`/qg ignore example-1`" in body
    assert "`/qg ignore example`" in body
    assert "`/qg ignore-file example.py`" in body


def test_in_progress_replaces_stale_report_with_pending_template() -> None:
    """Replace stale data with the canonical pending report."""
    github = FakeGitHub(
        [
            {
                "id": 8,
                "body": "<!-- monori-report: suppression -->\nold result",
                "user": {"login": "github-actions[bot]"},
            }
        ]
    )

    PullRequestReport.registered(github, 1, "suppression").mark_in_progress()

    patches = [call for call in github.calls if call[0] == "PATCH"]
    assert len(patches) == 1
    payload = cast("dict[str, JsonValue]", patches[0][2])
    body = cast("str", payload["body"])
    assert body.startswith("<!-- monori-report: suppression -->\n\n## ⏳ Lint suppression gate")
    assert "| Status | ⏳ In progress |" in body
    assert "old result" not in body


def test_command_reaction_lifecycle_replaces_acknowledgement_with_success() -> None:
    """Use one implementation for acknowledgement and final reactions."""
    github = FakeGitHub()
    lifecycle = CommandReactionLifecycle(github, 42)

    lifecycle.acknowledge()
    lifecycle.succeed()

    posts = [call for call in github.calls if call[0] == "POST"]
    assert posts[0][2] == {"content": "eyes"}
    assert posts[1][2] == {"content": "hooray"}
    assert all(path != "/user" for _, path, _ in github.calls)


def test_comment_body_is_bounded_with_an_exact_omission_notice() -> None:
    """Keep oversized reports within GitHub's hard comment-body limit."""
    original = "x" * (GITHUB_COMMENT_BODY_LIMIT + 500)

    bounded = bounded_comment_body(original)

    assert len(bounded) == GITHUB_COMMENT_BODY_LIMIT
    match = re.search(r"(\d+) characters omitted", bounded)
    assert match is not None
    notice_start = bounded.index("\n\n_Report truncated;")
    assert int(match.group(1)) == len(original) - notice_start


def test_empty_admin_commands_do_not_instruct_the_reader_to_post() -> None:
    """Avoid contradictory command instructions for a passing report."""
    body = render_report(
        ReportModel("bundle-size", ReportStatus.DONE, admin=admin_commands("bundle", [], []))
    )

    assert "No actionable findings in this run." in body
    assert "Post exactly one command" not in body
