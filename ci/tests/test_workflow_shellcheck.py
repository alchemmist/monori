"""Test extraction of shell scripts from GitHub Actions files."""

from pathlib import Path

from monori.ci.lib.workflow_shellcheck import embedded_scripts, write_scripts


def test_embedded_scripts_selects_shell_run_steps(tmp_path: Path) -> None:
    """Extract Bash scripts while excluding non-shell run steps."""
    workflow = tmp_path / "workflow.yaml"
    workflow.write_text(
        """
jobs:
  test:
    steps:
      - run: echo first
      - shell: python
        run: print('ignored')
      - shell: bash
        run: echo second
""".lstrip()
    )

    scripts = embedded_scripts(workflow)

    assert [(script.ordinal, script.source) for script in scripts] == [
        (1, "echo first"),
        (2, "echo second"),
    ]


def test_write_scripts_replaces_github_expressions(tmp_path: Path) -> None:
    """Produce standalone ShellCheck inputs without executable Actions expressions."""
    workflow = tmp_path / "workflow.yaml"
    workflow.write_text("steps:\n  - run: echo '${{ github.sha }}'\n")
    output = tmp_path / "scripts"

    write_scripts([workflow], output)

    scripts = list(output.iterdir())
    assert len(scripts) == 1
    assert scripts[0].read_text() == "echo '${GITHUB_ACTION_EXPRESSION}'"
