from typing import TYPE_CHECKING, cast

from monori.ci.quality_graph.commands import (
    QualityGraphCommand,
    command_request,
    command_targets_gate,
    command_text,
    help_body,
    is_finding_id,
    parse_command,
    validate_command,
)
from monori.ci.quality_graph.reporting import (
    ReportModel,
    ReportStatus,
    admin_commands,
    render_report,
)

if TYPE_CHECKING:
    from monori.common import JsonValue


class TestQualityGraphCommand:
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

    def test_ignore_file_targets_only_checks_with_file_approvals(self) -> None:
        command = parse_command("/qg ignore-file server/app.py")

        assert command is not None
        assert command_targets_gate(command, "object")
        assert command_targets_gate(command, "suppression")
        assert not command_targets_gate(command, "bundle")
        assert not command_targets_gate(command, "frontend")

    def test_old_commands_and_all_selector_are_rejected(self) -> None:
        assert parse_command("/ignore object-abc123") is None
        assert parse_command("/qg ignore all") is None
        assert parse_command("/qg ignore object-abc123 extra") is None

    def test_unknown_target_is_reported_by_validation(self) -> None:
        command = parse_command("/qg ignore unknown-target")

        assert command is not None
        assert validate_command(command) == "Unknown Quality Graph target: `unknown-target`"

    def test_finding_ids_require_a_registered_gate_prefix(self) -> None:
        assert is_finding_id("object-abc123")
        assert not is_finding_id("unknown-abc123")

    def test_help_is_generated_from_registered_check_metadata(self) -> None:
        body = help_body()

        for gate in ("object", "suppression", "bundle", "frontend"):
            assert f"{gate}-<id>" in body
        assert "selected files (object, suppression)" in body

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
        assert request.react

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
