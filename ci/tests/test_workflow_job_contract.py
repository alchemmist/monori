"""Verify every registered Quality Graph job through one portable contract."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from monori.ci.quality_graph.dashboard import (
    DashboardJob,
    DashboardModel,
    api_job_status,
    refresh_running_jobs,
    render_dashboard,
)
from monori.ci.quality_graph.job_results import (
    JobResult,
    JobStatus,
    append_job_summary,
    read_job_result,
    write_job_result,
)
from monori.ci.quality_graph.registry import (
    WorkflowJobDefinition,
    registered_checks,
    workflow_jobs,
)
from monori.common import JsonValue, array_value, object_value, string_value

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/pr-checks.yaml"
STATUS_CASES = (
    ("completed", "success", JobStatus.PASSED),
    ("completed", "failure", JobStatus.FAILED),
    ("completed", "skipped", JobStatus.SKIPPED),
)


def workflow_document() -> dict[str, JsonValue]:
    """Load the pull-request workflow as structured YAML data."""
    value: JsonValue = yaml.safe_load(WORKFLOW_PATH.read_text())
    return object_value(value, "pull request workflow")


def upload_artifact_name(definition: WorkflowJobDefinition) -> str:
    """Read the artifact contract from a job's structured composite action."""
    jobs = object_value(workflow_document().get("jobs"), "workflow jobs")
    job = object_value(jobs.get(definition.job_id), definition.job_id)
    steps = [object_value(step, "workflow step") for step in array_value(job.get("steps"), "steps")]
    quality_step = next(
        (step for step in steps if step.get("uses") == "./.github/actions/quality-job"),
        None,
    )
    if quality_step is not None:
        inputs = object_value(quality_step.get("with"), "quality job inputs")
        assert string_value(inputs.get("check-id"), "check id") == definition.job_id
        action_path = REPOSITORY_ROOT / ".github/actions/quality-job/action.yml"
    else:
        local_action = next(
            string_value(step.get("uses"), "local action")
            for step in steps
            if isinstance(step.get("uses"), str)
            and string_value(step.get("uses"), "local action").startswith("./.github/actions/")
        )
        action_path = REPOSITORY_ROOT / f"{local_action.removeprefix('./')}" / "action.yml"
    action_value: JsonValue = yaml.safe_load(action_path.read_text())
    action = object_value(action_value, "composite action")
    runs = object_value(action.get("runs"), "action runs")
    action_steps = [
        object_value(step, "action step") for step in array_value(runs.get("steps"), "action steps")
    ]
    if quality_step is not None:
        command = action_steps[0]
        assert command.get("id") == "command"
        assert "monori.ci.quality_graph.run_job" in string_value(command.get("run"), "job runner")
        enforce = action_steps[-1]
        assert enforce.get("if") == "always()"
        environment = object_value(enforce.get("env"), "enforcement environment")
        assert environment.get("EXIT_CODE") == "${{ steps.command.outputs.exit_code }}"
    upload = next(
        step
        for step in action_steps
        if isinstance(step.get("uses"), str)
        and string_value(step.get("uses"), "upload action").startswith("actions/upload-artifact@")
    )
    inputs = object_value(upload.get("with"), "upload inputs")
    return string_value(inputs.get("name"), "artifact name").replace(
        "${{ inputs.check-id }}", definition.job_id
    )


@pytest.mark.parametrize("definition", workflow_jobs().values(), ids=lambda item: item.job_id)
def test_registered_job_contract(definition: WorkflowJobDefinition, tmp_path: Path) -> None:
    """Keep workflow, artifacts, summaries, and dashboard status mapping aligned."""
    jobs = object_value(workflow_document().get("jobs"), "workflow jobs")
    job = object_value(jobs.get(definition.job_id), definition.job_id)
    assert string_value(job.get("name"), "job name") == definition.title
    if definition.gate is not None:
        check = registered_checks()[definition.gate]
        assert check.definition is definition
        assert definition.report_marker is not None
    assert upload_artifact_name(definition) == (
        f"quality-result-{definition.job_id}-${{{{ github.run_attempt }}}}"
    )

    for api_status, conclusion, expected in STATUS_CASES:
        result = JobResult(definition.job_id, definition.title, expected)
        result_path = tmp_path / f"{definition.job_id}-{expected.value}.json"
        summary_path = tmp_path / f"{definition.job_id}-{expected.value}.md"
        write_job_result(result_path, result)
        append_job_summary(summary_path, result)
        assert read_job_result(result_path).check_id == definition.job_id
        assert f"quality-graph-{definition.job_id}" in summary_path.read_text()
        api_job: dict[str, JsonValue] = {
            "name": definition.title,
            "status": api_status,
            "conclusion": conclusion,
            "html_url": "https://example.test/job",
        }
        assert api_job_status(api_job) is expected
        dashboard = render_dashboard(
            DashboardModel(
                expected,
                "Contract",
                1,
                1,
                "head",
                (
                    DashboardJob(
                        definition.job_id,
                        definition.title,
                        JobStatus.WAITING,
                        "https://example.test/summary",
                        "https://example.test/logs",
                    ),
                ),
            )
        )
        refreshed = refresh_running_jobs(
            dashboard,
            {definition.title: api_job},
            "https://example.test/run",
        )
        assert f"| {definition.title} | {expected.label} |" in refreshed
