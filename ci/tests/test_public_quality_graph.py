from pathlib import Path

import yaml


def test_python_gates_run_inside_the_locked_uv_environment() -> None:
    graph = yaml.safe_load(Path("quality-graph.yml").read_text())

    for node_id in ("triple-quotes", "suppressions", "object-annotations", "time-bombs"):
        command = graph["nodes"][node_id]["run"]
        assert command.startswith("uv run --locked --group quality-graph qg-python-")
