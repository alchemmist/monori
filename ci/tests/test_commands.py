import unittest
from typing import cast, override
from unittest import mock

from ci.lib.json import JsonValue
from ci.quality_graph.commands import (
    QualityGraphCommand,
    command_targets_gate,
    command_text,
    parse_command,
    rerun_workflow,
    set_comment_reaction,
    upsert_status,
    validate_command,
)


class FakeGitHub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, JsonValue]] = []

    def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        self.calls.append((method, path, payload))
        if path == "/user":
            return {"login": "github-actions[bot]"}
        if path.endswith("/reactions") and method == "GET":
            return [{"id": 7, "user": {"login": "github-actions[bot]"}, "content": "eyes"}]
        if path.endswith("/comments?per_page=100&page=1"):
            return [
                {
                    "id": 1,
                    "body": "<!-- monori-report: quality-graph -->\nold",
                    "user": {"login": "author"},
                },
                {
                    "id": 2,
                    "body": "<!-- monori-report: quality-graph -->\nold",
                    "user": {"login": "github-actions[bot]"},
                },
            ]
        return None


class QualityGraphCommandTest(unittest.TestCase):
    def test_full_name_and_alias_share_the_same_command(self) -> None:
        expected = QualityGraphCommand("ignore", ("object-abc123", "suppression-def456"))

        assert parse_command("/quality-graph ignore object-abc123,suppression-def456") == expected
        assert parse_command("/qg ignore object-abc123,suppression-def456") == expected

    def test_gate_name_targets_all_findings_of_that_type(self) -> None:
        command = parse_command("/qg ignore object,suppression")

        assert command is not None
        assert command_targets_gate(command, "object")
        assert command_targets_gate(command, "suppression")
        assert not command_targets_gate(command, "bundle")

    def test_old_commands_and_all_selector_are_rejected(self) -> None:
        assert parse_command("/ignore object-abc123") is None
        assert parse_command("/qg ignore all") is None
        assert parse_command("/qg ignore object-abc123 extra") is None

    def test_unknown_target_is_reported_by_validation(self) -> None:
        command = parse_command("/qg ignore unknown-target")

        assert command is not None
        assert validate_command(command) == "Unknown Quality Graph target: `unknown-target`"

    def test_command_text_is_canonical(self) -> None:
        command = QualityGraphCommand("remove-ignore", ("object-abc123", "suppression-def456"))

        assert command_text(command) == "/qg remove-ignore object-abc123,suppression-def456"

    def test_reaction_replaces_the_bot_reaction(self) -> None:
        github = FakeGitHub()

        set_comment_reaction(github, 42, "hooray")

        assert ("DELETE", "/issues/comments/42/reactions/7", None) in github.calls
        assert ("POST", "/issues/comments/42/reactions", {"content": "hooray"}) in github.calls

    def test_status_updates_only_the_bot_owned_quality_graph_comment(self) -> None:
        github = FakeGitHub()

        upsert_status(github, 42, "## Quality Graph status")

        assert (
            "PATCH",
            "/issues/comments/2",
            cast(
                "JsonValue",
                {"body": "<!-- monori-report: quality-graph -->\n\n## Quality Graph status\n"},
            ),
        ) in github.calls
        assert ("PATCH", "/issues/comments/1", mock.ANY) not in github.calls

    def test_rerun_reads_workflow_runs_from_the_api_response_object(self) -> None:
        class WorkflowGitHub(FakeGitHub):
            @override
            def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
                self.calls.append((method, path, payload))
                if path == "/pulls/42":
                    return {"head": {"sha": "abc", "ref": "feature"}}
                if path.startswith("/actions/workflows/pr-checks.yaml/runs?"):
                    return {
                        "total_count": 1,
                        "workflow_runs": [{"id": 9, "head_sha": "abc"}],
                    }
                return None

        github = WorkflowGitHub()

        rerun_workflow(github, 42)

        assert ("POST", "/actions/runs/9/rerun-failed-jobs", None) in github.calls


if __name__ == "__main__":
    unittest.main()
