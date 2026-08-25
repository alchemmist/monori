from pathlib import Path

import yaml


def test_python_gates_run_inside_the_locked_uv_environment() -> None:
    graph = yaml.safe_load(Path("quality-graph.yml").read_text())

    for node_id in ("triple-quotes", "suppressions", "object-annotations", "time-bombs"):
        command = graph["nodes"][node_id]["run"]
        assert command.startswith("uv run --locked --group quality-graph qg-python-")


def test_mutation_and_performance_inputs_are_available() -> None:
    graph = yaml.safe_load(Path("quality-graph.yml").read_text())
    pyproject = Path("pyproject.toml").read_text()

    assert '"quality-graph.yml"' in pyproject
    assert graph["nodes"]["frontend-performance"]["profile"] == "performance"
    setup = graph["profiles"]["performance"]["setup"]
    assert setup == [
        {
            "run": "npx playwright install --with-deps chromium",
            "working-directory": "tools/frontend-perf",
        }
    ]
