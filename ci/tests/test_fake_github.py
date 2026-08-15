"""Test the fake GitHub state model independently of the HTTP adapter."""

from monori.ci.testkit.fake_github import FakeGitHubState


def test_reset_and_snapshot_preserve_observable_repository_state() -> None:
    """Load a scenario fixture and expose the same state through a snapshot."""
    state = FakeGitHubState()

    state.reset(
        {
            "pulls": [{"number": 7, "body": "body"}],
            "comments": [
                {
                    "id": 12,
                    "issue_number": 7,
                    "body": "command",
                    "user": {"login": "admin"},
                    "reactions": [],
                }
            ],
            "issue_labels": {"7": ["failed"]},
            "permissions": {"admin": "admin"},
            "workflow_runs": [{"id": 20}],
        }
    )

    snapshot = state.snapshot()
    assert snapshot["pulls"] == [{"number": 7, "body": "body"}]
    assert snapshot["issue_labels"] == {"7": ["failed"]}
    assert snapshot["permissions"] == {"admin": "admin"}


def test_comments_and_reactions_receive_stable_incrementing_ids() -> None:
    """Allocate observable identifiers without exposing request-call history."""
    state = FakeGitHubState()
    state.reset({})

    comment = state.create_comment(7, "report")
    reaction = state.add_reaction(1, "eyes")

    assert comment["id"] == 1
    assert reaction["id"] == 1
    assert state.snapshot()["comments"] == [
        {
            "id": 1,
            "issue_number": 7,
            "body": "report",
            "user": {"login": "github-actions[bot]"},
            "reactions": [reaction],
        }
    ]
