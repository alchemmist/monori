from pathlib import Path

import yaml


def test_python_gates_run_inside_the_locked_uv_environment() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/quality-graph.yml").read_text())

    for node_id in ("triple-quotes", "suppressions", "object-annotations", "time-bombs"):
        command = next(
            step["run"]
            for step in workflow["jobs"][node_id]["steps"]
            if step.get("id") == "quality-command"
        )
        assert command.startswith("uv run --locked --group quality-graph qg-python-")


def test_mutation_and_performance_inputs_are_available() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/quality-graph.yml").read_text())

    setup = workflow["jobs"]["frontend-performance"]["steps"]
    assert {
        "run": "npx playwright install --with-deps chromium",
        "working-directory": "tools/frontend-perf",
    } in setup
    makefile = Path("Makefile").read_text()
    assert "common '*.py'" not in makefile
