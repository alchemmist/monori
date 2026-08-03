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

        self.assertEqual(
            parse_command("/quality-graph ignore object-abc123,suppression-def456"),
            expected,
        )
        self.assertEqual(parse_command("/qg ignore object-abc123,suppression-def456"), expected)

    def test_gate_name_targets_all_findings_of_that_type(self) -> None:
        command = parse_command("/qg ignore object,suppression")

        self.assertIsNotNone(command)
        assert command is not None
        self.assertTrue(command_targets_gate(command, "object"))
        self.assertTrue(command_targets_gate(command, "suppression"))
        self.assertFalse(command_targets_gate(command, "bundle"))

    def test_old_commands_and_all_selector_are_rejected(self) -> None:
        self.assertIsNone(parse_command("/ignore object-abc123"))
        self.assertIsNone(parse_command("/qg ignore all"))
        self.assertIsNone(parse_command("/qg ignore object-abc123 extra"))

    def test_unknown_target_is_reported_by_validation(self) -> None:
        command = parse_command("/qg ignore unknown-target")

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(
            validate_command(command), "Unknown Quality Graph target: `unknown-target`"
        )

    def test_command_text_is_canonical(self) -> None:
        command = QualityGraphCommand("remove-ignore", ("object-abc123", "suppression-def456"))

        self.assertEqual(
            command_text(command), "/qg remove-ignore object-abc123,suppression-def456"
        )

    def test_reaction_replaces_the_bot_reaction(self) -> None:
        github = FakeGitHub()

        set_comment_reaction(github, 42, "hooray")

        self.assertIn(("DELETE", "/issues/comments/42/reactions/7", None), github.calls)
        self.assertIn(
            ("POST", "/issues/comments/42/reactions", {"content": "hooray"}),
            github.calls,
        )

    def test_status_updates_only_the_bot_owned_quality_graph_comment(self) -> None:
        github = FakeGitHub()

        upsert_status(github, 42, "## Quality Graph status")

        self.assertIn(
            (
                "PATCH",
                "/issues/comments/2",
                cast(
                    "JsonValue",
                    {"body": "<!-- monori-report: quality-graph -->\n\n## Quality Graph status\n"},
                ),
            ),
            github.calls,
        )
        self.assertNotIn(("PATCH", "/issues/comments/1", mock.ANY), github.calls)

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

        self.assertIn(("POST", "/actions/runs/9/rerun-failed-jobs", None), github.calls)


if __name__ == "__main__":
    unittest.main()
