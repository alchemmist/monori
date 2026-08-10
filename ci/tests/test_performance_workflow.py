from pathlib import Path
from typing import TypedDict, cast

import yaml

from monori.common import JsonObject, JsonValue, decode_json, object_value, string_value

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/performance.yaml"
ACTIONS = {
    "backend-and-e2e": REPOSITORY_ROOT / ".github/actions/backend-performance/action.yml",
    "frontend": REPOSITORY_ROOT / ".github/actions/frontend-lab-performance/action.yml",
}
LOAD_RUNNER = REPOSITORY_ROOT / "scripts/load.sh"
FRONTEND_CONFIG = REPOSITORY_ROOT / "tools/frontend-perf/config.json"
FRONTEND_BASELINE = REPOSITORY_ROOT / "tools/frontend-perf/baseline.mjs"


class WorkflowJob(TypedDict):
    steps: list[dict[str, JsonValue]]


def load_yaml(path: Path) -> dict[str, JsonValue]:
    return cast("dict[str, JsonValue]", yaml.safe_load(path.read_text()))


def test_performance_workflow_is_manual_and_read_only() -> None:
    source = WORKFLOW_PATH.read_text()
    workflow = load_yaml(WORKFLOW_PATH)
    assert "workflow_dispatch:" in source
    assert "pull_request:" not in source
    assert "schedule:" not in source
    assert workflow["permissions"] == {"contents": "read"}


def test_performance_jobs_delegate_to_local_actions() -> None:
    workflow = load_yaml(WORKFLOW_PATH)
    jobs = cast("dict[str, WorkflowJob]", workflow["jobs"])
    expected = {
        "backend-and-e2e": "./.github/actions/backend-performance",
        "frontend": "./.github/actions/frontend-lab-performance",
    }
    for job_id, action in expected.items():
        uses = [step.get("uses") for step in jobs[job_id]["steps"]]
        assert uses == ["actions/checkout@v7", action]


def test_performance_actions_preserve_reports_before_enforcement() -> None:
    for path in ACTIONS.values():
        action = load_yaml(path)
        runs = cast("dict[str, JsonValue]", action["runs"])
        steps = cast("list[dict[str, JsonValue]]", runs["steps"])
        upload_index = next(
            index
            for index, step in enumerate(steps)
            if step.get("uses") == "actions/upload-artifact@v7"
        )
        enforce_index = next(
            index
            for index, step in enumerate(steps)
            if str(step.get("name", "")).startswith("Enforce")
        )
        assert steps[upload_index]["if"] == "always()"
        assert steps[enforce_index]["if"] == "always()"
        assert upload_index < enforce_index


def test_backend_runner_uses_workspace_permissions_and_project_python() -> None:
    action = load_yaml(ACTIONS["backend-and-e2e"])
    runs = cast("dict[str, JsonValue]", action["runs"])
    steps = cast("list[dict[str, JsonValue]]", runs["steps"])
    runner = LOAD_RUNNER.read_text()

    assert steps[0].get("uses") == "./.github/actions/setup-project"
    assert steps[0].get("with") == {"python-profile": "ci"}
    assert '--user "$(id -u):$(id -g)"' in runner
    assert "uv run --locked python performance/report.py" in runner


def test_backend_runner_resets_state_before_each_level() -> None:
    runner = LOAD_RUNNER.read_text()
    setup, level_runner = runner.split("run_level() {", 1)
    level_runner = level_runner.split("\n}", 1)[0]

    assert "stack build back front" in setup
    reset = "stack down --volumes --remove-orphans"
    start = "stack up --detach back front"
    assert reset in level_runner
    assert level_runner.index(reset) < level_runner.index(start)


def test_frontend_sla_declares_existing_route_debt_explicitly() -> None:
    config = object_value(decode_json(FRONTEND_CONFIG.read_text()), "frontend config")
    routes = config["lighthouseRoutes"]
    assert isinstance(routes, list)
    route_slas: dict[str, JsonObject] = {}
    for route in routes:
        route_object = object_value(route, "frontend route")
        route_id = string_value(route_object.get("id"), "frontend route id")
        route_slas[route_id] = object_value(route_object.get("sla", {}), "frontend route SLA")

    assert route_slas["dashboard"] == {"total-blocking-time": 2000}
    assert route_slas["transactions"] == {"total-blocking-time": 800}
    assert "route.sla?.[metricId]" in FRONTEND_BASELINE.read_text()
