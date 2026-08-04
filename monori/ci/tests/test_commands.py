import unittest
from typing import cast, override
from unittest import mock

from monori.ci.quality_graph.commands import (
    CommandRequest,
    QualityGraphCommand,
    command_request,
    command_targets_gate,
    command_text,
    parse_command,
    process_command,
    rerun_workflow,
    set_comment_reaction,
    upsert_status,
    validate_command,
)
from monori.ci.quality_graph.reporting import (
    ReportModel,
    ReportStatus,
    admin_commands,
    render_report,
)
from monori.common import JsonValue


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

    def test_checked_report_control_reuses_the_command_parser(self) -> None:
        body = render_report(
            ReportModel(
                "suppression",
                ReportStatus.FAIL,
                admin=admin_commands("suppression", ["suppression-abc123"], []),
            )
        )
        checked = body.replace("- [ ]", "- [x]", 1)
        event = cast(
            "dict[str, JsonValue]",
            {
                "action": "edited",
                "issue": {"number": 42, "pull_request": {"url": "pull"}},
                "comment": {
                    "id": 8,
                    "body": checked,
                    "user": {"login": "github-actions[bot]"},
                },
                "sender": {"login": "admin"},
                "changes": {"body": {"from": body}},
            },
        )

        request = command_request(event)

        assert request is not None
        assert parse_command(request.body) == QualityGraphCommand("ignore", ("suppression-abc123",))
        assert request.login == "admin"
        assert request.pull_request_number == 42
        assert not request.react

    def test_unchecked_report_control_becomes_remove_ignore(self) -> None:
        checked = render_report(
            ReportModel(
                "suppression",
                ReportStatus.DONE,
                admin=admin_commands("suppression", [], ["suppression-abc123"]),
            )
        )
        unchecked = checked.replace("- [x]", "- [ ]", 1)
        event = cast(
            "dict[str, JsonValue]",
            {
                "action": "edited",
                "issue": {"number": 42, "pull_request": {"url": "pull"}},
                "comment": {
                    "id": 8,
                    "body": unchecked,
                    "user": {"login": "github-actions[bot]"},
                },
                "sender": {"login": "admin"},
                "changes": {"body": {"from": checked}},
            },
        )

        request = command_request(event)

        assert request is not None
        assert parse_command(request.body) == QualityGraphCommand(
            "remove-ignore", ("suppression-abc123",)
        )

    def test_non_admin_checkbox_edit_does_not_write_or_rerun(self) -> None:
        class NonAdminGitHub(FakeGitHub):
            @override
            def request(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
                self.calls.append((method, path, payload))
                if path.endswith("/permission"):
                    return {"permission": "write"}
                return None

        github = NonAdminGitHub()

        process_command(
            github,
            CommandRequest(
                8,
                "/qg ignore suppression-abc123",
                "contributor",
                42,
                react=False,
            ),
        )

        assert github.calls == [
            ("GET", "/collaborators/contributor/permission", None),
        ]

    def test_checkbox_control_is_ignored_on_user_owned_comment(self) -> None:
        body = render_report(
            ReportModel(
                "suppression",
                ReportStatus.FAIL,
                admin=admin_commands("suppression", ["suppression-abc123"], []),
            )
        )
        event = cast(
            "dict[str, JsonValue]",
            {
                "action": "edited",
                "issue": {"number": 42, "pull_request": {"url": "pull"}},
                "comment": {
                    "id": 8,
                    "body": body.replace("- [ ]", "- [x]", 1),
                    "user": {"login": "contributor"},
                },
                "sender": {"login": "admin"},
                "changes": {"body": {"from": body}},
            },
        )

        assert command_request(event) is None

    def test_reaction_replaces_the_bot_reaction(self) -> None:
        github = FakeGitHub()

        set_comment_reaction(github, 42, "hooray")

        assert ("DELETE", "/issues/comments/42/reactions/7", None) in github.calls
        assert ("POST", "/issues/comments/42/reactions", {"content": "hooray"}) in github.calls
        assert not any(path == "/user" for _, path, _ in github.calls)

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
