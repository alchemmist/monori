"""Test the shared approval and gate-state lifecycle."""

import re
from dataclasses import dataclass

from monori.ci.quality_graph.base import ApprovalLifecycle, ApprovalRequest
from monori.ci.quality_graph.commands import parse_command
from monori.common import JsonValue


@dataclass(frozen=True)
class Finding:
    """Provide a minimal finding accepted by the shared lifecycle."""

    path: str
    finding_id: str


class FakeGitHub:
    """Record state changes and expose one collaborator permission."""

    def __init__(self, permission: str = "admin") -> None:
        """Initialize the fake with a collaborator permission."""
        self.permission = permission
        self.calls: list[tuple[str, str, JsonValue]] = []

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        """Record a request and return permission fixture data."""
        self.calls.append((method, path, payload))
        if path.startswith("/collaborators/"):
            return {"permission": self.permission}
        return None


LIFECYCLE = ApprovalLifecycle(
    "example",
    "example-",
    re.compile(r"<!-- example-approvals: ([a-z0-9,-]*) -->"),
    "<!-- example-approvals: {ids} -->",
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
