from typing import TYPE_CHECKING, cast

import pytest

from monori.ci.quality_graph.commands import (
    QualityGraphCommand,
    command_request,
    command_targets_gate,
    command_text,
    control_commands,
    finding_gate,
    help_body,
    is_finding_id,
    parse_command,
    pull_request_number,
    validate_command,
)
from monori.ci.quality_graph.registry import workflow_job_for_gate
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
        command = parse_command("/qg ignore object-annotations,suppressions")

        assert command is not None
        assert command_targets_gate(command, "object")
        assert command_targets_gate(command, "suppression")
        assert not command_targets_gate(command, "bundle")

        legacy = parse_command("/qg ignore object,suppression")
        assert legacy is not None
        assert validate_command(legacy) is None
        assert command_targets_gate(legacy, "object")
        assert command_targets_gate(legacy, "suppression")

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

    def test_validation_covers_status_help_files_and_every_target(self) -> None:
        assert validate_command(QualityGraphCommand("help")) is None
        assert validate_command(QualityGraphCommand("status")) is None
        assert (
            validate_command(QualityGraphCommand("ignore-file"))
            == "At least one file path is required"
        )
        assert validate_command(QualityGraphCommand("ignore-file", ("server/app.py",))) is None
        assert (
            validate_command(
                QualityGraphCommand("ignore", ("object-annotations", "unknown-target"))
            )
            == "Unknown Quality Graph target: `unknown-target`"
        )

    def test_finding_ids_require_a_registered_gate_prefix(self) -> None:
        assert is_finding_id("object-abc123")
        assert not is_finding_id("unknown-abc123")

    def test_help_is_generated_from_registered_check_metadata(self) -> None:
        body = help_body()

        for gate in ("object", "suppression", "bundle", "frontend"):
            assert f"{gate}-<id>" in body
        assert "selected files (object-annotations, suppressions)" in body
        assert "/qg ignore object-annotations,suppressions,bundle-size,frontend-performance" in body
        assert (
            body == "Only repository administrators may execute state-changing commands.\n\n"
            "- `/qg ignore object-<id>,suppression-<id>,bundle-<id>,frontend-<id>` — "
            "ignore selected findings\n"
            "- `/qg ignore object-annotations,suppressions,bundle-size,frontend-performance` — "
            "ignore all current findings of selected types\n"
            "- `/qg ignore-file path/to/file` — ignore findings in selected files "
            "(object-annotations, suppressions)\n"
            "- `/qg remove-ignore object-<id>,suppression-<id>,bundle-<id>,frontend-<id>` — "
            "remove selected ignores\n"
            "- `/qg status` — show the current command status\n"
            "- `/qg help` — show this help"
        )

    def test_unknown_internal_gate_has_an_actionable_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown Quality Graph gate: missing"):
            workflow_job_for_gate("missing")

    def test_command_text_is_canonical(self) -> None:
        command = QualityGraphCommand("remove-ignore", ("object-abc123", "suppression-def456"))

        assert command_text(command) == "/qg remove-ignore object-abc123,suppression-def456"

    def test_checked_report_control_reuses_the_command_parser(self) -> None:
        body = render_report(
            ReportModel(
                "suppression",
                ReportStatus.FAILED,
                admin=admin_commands("suppression", ["suppression-abc123"], []),
            )
        ).summary
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
                ReportStatus.PASSED,
                admin=admin_commands("suppression", [], ["suppression-abc123"]),
            )
        ).summary
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
                ReportStatus.FAILED,
                admin=admin_commands("suppression", ["suppression-abc123"], []),
            )
        ).summary
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

    def test_parser_rejects_arguments_for_read_only_commands(self) -> None:
        assert parse_command("/qg help object") is None
        assert parse_command("/qg status object") is None
        assert parse_command("/qg ignore") is None
        assert parse_command("/qg ignore object,,suppression") is None

    def test_validation_handles_empty_and_malformed_targets(self) -> None:
        assert validate_command(QualityGraphCommand("ignore")) == "At least one target is required"
        assert (
            validate_command(QualityGraphCommand("ignore-file", ()))
            == "At least one file path is required"
        )
        assert finding_gate("object-") is None
        assert finding_gate("missing-value") is None
        assert not command_targets_gate(QualityGraphCommand("ignore", ("object-a",)), "missing")

    def test_control_decoder_rejects_invalid_payloads(self) -> None:
        assert control_commands("monori-qg-control:not-base64!") is None
        assert control_commands("monori-qg-control:b25lLWxpbmU") is None

    def test_event_parser_rejects_incomplete_and_ambiguous_edits(self) -> None:
        assert command_request({}) is None
        assert command_request({"comment": {"id": "invalid"}}) is None
        assert pull_request_number({"issue": {"number": 42}}) is None
        assert pull_request_number({"issue": {"number": "42", "pull_request": {}}}) is None

        body = render_report(
            ReportModel(
                "suppression",
                ReportStatus.FAILED,
                admin=admin_commands(
                    "suppression",
                    ["suppression-first", "suppression-second"],
                    [],
                ),
            )
        ).summary
        unchanged = cast(
            "dict[str, JsonValue]",
            {
                "action": "created",
                "comment": {
                    "id": 8,
                    "body": body,
                    "user": {"login": "github-actions[bot]"},
                },
                "changes": {"body": {"from": body}},
                "issue": {"number": 42, "pull_request": {}},
                "sender": {"login": "admin"},
            },
        )
        assert command_request(unchanged) is None

        changed_twice = body.replace("- [ ]", "- [x]")
        unchanged["action"] = "edited"
        comment = cast("dict[str, JsonValue]", unchanged["comment"])
        comment["body"] = changed_twice
        assert command_request(unchanged) is None
