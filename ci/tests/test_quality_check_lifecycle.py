"""Test the shared approval and gate-state lifecycle."""

import re
from dataclasses import dataclass

from monori.ci.quality_graph.base import ApprovalLifecycle, ApprovalRequest
from monori.ci.quality_graph.commands import encode_command, parse_command
from monori.common import JsonValue


@dataclass(frozen=True)
class Finding:
    """Provide a minimal finding accepted by the shared lifecycle."""

    path: str
    finding_id: str


class FakeGitHub:
    """Record state changes and expose one collaborator permission."""

    def __init__(
        self,
        permission: str = "admin",
        comments: dict[int, dict[str, JsonValue]] | None = None,
    ) -> None:
        """Initialize the fake with a collaborator permission."""
        self.permission = permission
        self.comments = comments or {}
        self.calls: list[tuple[str, str, JsonValue]] = []

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Record a request and return permission fixture data."""
        self.calls.append((method, path, payload))
        if path.startswith("/collaborators/"):
            return {"permission": self.permission}
        if method == "GET" and path.startswith("/issues/comments/"):
            return self.comments.get(int(path.rsplit("/", maxsplit=1)[1]))
        return None


LIFECYCLE = ApprovalLifecycle(
    "example",
    "example-",
    re.compile(r"<!-- example-approvals: ([a-z0-9,-]*) -->"),
    "<!-- example-approvals: {ids} -->",
)

PENDING_LIFECYCLE = ApprovalLifecycle(
    "bundle",
    "bundle-",
    re.compile(r"<!-- bundle-approvals: ([a-z0-9,-]*) -->"),
    "<!-- bundle-approvals: {ids} -->",
    re.compile(r"<!-- bundle-pending: (\d+)(?: ([A-Za-z0-9_-]+))? -->"),
)


def test_lifecycle_applies_admin_commands_and_persists_state() -> None:
    """Apply a gate-wide command through the reusable lifecycle."""
    github = FakeGitHub()
    command = parse_command("/qg ignore example")
    assert command is not None
    request = ApprovalRequest(github, 7, "", command, "admin", [])

    result = LIFECYCLE.sync(request, [Finding("example.py", "one")])

    assert result.approved == {"one"}
    assert result.authorized
    assert result.changed
    assert (
        "PATCH",
        "/pulls/7",
        {"body": "<!-- example-approvals: one -->"},
    ) in github.calls


def test_lifecycle_rejects_state_changes_from_non_admins() -> None:
    """Leave approvals unchanged when a non-admin submits a command."""
    github = FakeGitHub("write")
    command = parse_command("/qg ignore example-one")
    assert command is not None
    body = "<!-- example-approvals:  -->"

    result = LIFECYCLE.sync(
        ApprovalRequest(github, 7, body, command, "contributor", []),
        [Finding("example.py", "one")],
    )

    assert result.approved == set()
    assert not result.authorized
    assert not any(method == "PATCH" for method, _, _ in github.calls)


def test_pending_command_rejects_forged_encoded_marker() -> None:
    """Reject an encoded PR-body command without bot-owned authorization."""
    command = parse_command("/qg ignore bundle")
    assert command is not None
    encoded = encode_command(command)
    github = FakeGitHub(
        comments={
            1: {
                "body": f"<!-- monori-qg-authorized: bundle {encoded} -->",
                "user": {"login": "fork-author"},
            }
        }
    )

    resolved = PENDING_LIFECYCLE.pending_command(github, f"<!-- bundle-pending: 1 {encoded} -->")

    assert resolved is None


def test_pending_command_accepts_bot_owned_one_time_authorization() -> None:
    """Accept an encoded command only when a managed bot comment authorizes it."""
    command = parse_command("/qg ignore bundle")
    assert command is not None
    encoded = encode_command(command)
    github = FakeGitHub(
        comments={
            7: {
                "body": f"report\n<!-- monori-qg-authorized: bundle {encoded} -->",
                "user": {"login": "github-actions[bot]"},
            }
        }
    )

    resolved = PENDING_LIFECYCLE.pending_command(github, f"<!-- bundle-pending: 7 {encoded} -->")

    assert resolved == command

    PENDING_LIFECYCLE.consume_pending(github, f"<!-- bundle-pending: 7 {encoded} -->")

    assert github.calls[-1] == (
        "PATCH",
        "/issues/comments/7",
        {"body": "report"},
    )


def test_pending_command_rejects_missing_source_comment() -> None:
    """Ignore a forged marker that references no GitHub comment."""
    command = parse_command("/qg ignore bundle")
    assert command is not None
    encoded = encode_command(command)

    resolved = PENDING_LIFECYCLE.pending_command(
        FakeGitHub(), f"<!-- bundle-pending: 404 {encoded} -->"
    )

    assert resolved is None
