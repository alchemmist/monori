"""Protect Monori's Python package boundaries and dependency direction."""

import ast
import tomllib
from pathlib import Path
from typing import cast

from monori.common import JsonValue, array_value, object_value, string_value

REPOSITORY_ROOT = Path(__file__).parents[5]
COMPONENT_ROOTS = {
    "common": REPOSITORY_ROOT / "common" / "src" / "monori" / "common",
    "ci": REPOSITORY_ROOT / "ci" / "src" / "monori" / "ci",
    "server": REPOSITORY_ROOT / "server" / "src" / "monori" / "server",
}


def python_modules(root: Path) -> list[Path]:
    """Return all Python modules below a package directory."""
    return sorted(root.rglob("*.py"))


def parsed_imports(path: Path) -> list[ast.Import | ast.ImportFrom]:
    """Return import nodes from one Python module."""
    tree = ast.parse(path.read_text(), filename=str(path))
    return [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]


def project(path: Path) -> dict[str, JsonValue]:
    """Load one project file as a typed TOML mapping."""
    return cast("dict[str, JsonValue]", tomllib.loads(path.read_text()))


def section(document: dict[str, JsonValue], *names: str) -> dict[str, JsonValue]:
    """Traverse nested TOML tables and return the requested object."""
    current: JsonValue = document
    for name in names:
        current = object_value(current, name).get(name)
    return object_value(current, ".".join(names))


def project_dependencies(document: dict[str, JsonValue]) -> list[str]:
    """Return one project's declared dependency strings."""
    values = array_value(section(document, "project").get("dependencies"), "dependencies")
    return [string_value(value, "dependency") for value in values]


def test_root_is_a_virtual_workspace() -> None:
    """Keep the repository root from building an umbrella Python package."""
    root = project(REPOSITORY_ROOT / "pyproject.toml")

    assert section(root, "project").get("name") == "monori-workspace"
    assert section(root, "tool", "uv").get("package") is False
    assert "build-system" not in root


def test_components_are_independent_namespace_packages() -> None:
    """Build every component as its own distribution in the monori namespace."""
    for component, package_root in COMPONENT_ROOTS.items():
        metadata = project(REPOSITORY_ROOT / component / "pyproject.toml")

        assert section(metadata, "project").get("name") == f"monori-{component}"
        assert section(metadata, "build-system").get("build-backend") == "hatchling.build"
        assert section(metadata, "tool", "hatch", "build", "targets", "wheel").get("packages") == [
            "src/monori"
        ]
        tool = object_value(metadata.get("tool"), "tool")
        uv = object_value(tool.get("uv", {}), "tool.uv")
        assert uv.get("package") is not False
        assert package_root.is_dir()
        assert not (package_root.parent / "__init__.py").exists()


def test_component_dependency_graph_has_no_umbrella_package() -> None:
    """Require consumers to depend directly on common instead of all source code."""
    common = project(REPOSITORY_ROOT / "common" / "pyproject.toml")
    ci = project(REPOSITORY_ROOT / "ci" / "pyproject.toml")
    server = project(REPOSITORY_ROOT / "server" / "pyproject.toml")

    assert project_dependencies(common) == []
    for consumer in (ci, server):
        dependencies = project_dependencies(consumer)
        assert "monori-common" in dependencies
        assert "monori" not in dependencies


def test_internal_imports_are_absolute_and_namespaced() -> None:
    """Reject relative imports and legacy top-level package names."""
    violations: list[str] = []
    for package_root in COMPONENT_ROOTS.values():
        for path in python_modules(package_root):
            for imported in parsed_imports(path):
                if isinstance(imported, ast.ImportFrom):
                    if imported.level:
                        violations.append(f"{path}: relative import")
                    module = imported.module or ""
                    if module.split(".", 1)[0] in {"app", "ci", "tests"}:
                        violations.append(f"{path}: {module}")
                else:
                    violations.extend(
                        f"{path}: {alias.name}"
                        for alias in imported.names
                        if alias.name.split(".", 1)[0] in {"app", "ci", "tests"}
                    )

    assert violations == []


def test_ci_library_does_not_depend_on_quality_graph() -> None:
    """Keep reusable CI primitives below workflow-specific Quality Graph code."""
    violations = [
        str(path)
        for path in python_modules(COMPONENT_ROOTS["ci"] / "lib")
        for imported in parsed_imports(path)
        if isinstance(imported, ast.ImportFrom)
        and (imported.module or "").startswith("monori.ci.quality_graph")
    ]

    assert violations == []


def test_quality_gates_use_shared_github_and_lifecycle_implementations() -> None:
    """Prevent gate modules from restoring private API clients and permission logic."""
    checks = COMPONENT_ROOTS["ci"] / "quality_graph" / "checks"
    violations: list[str] = []
    for path in checks.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "GitHub":
                violations.append(f"{path}: private GitHub client")
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "is_admin"
            ):
                violations.append(f"{path}: private is_admin")

    assert violations == []


def test_json_value_has_one_definition() -> None:
    """Keep the recursive JSON type in the common package only."""
    definitions = [
        path
        for package_root in COMPONENT_ROOTS.values()
        for path in python_modules(package_root)
        if any(
            isinstance(node, ast.TypeAlias) and node.name.id == "JsonValue"
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path)))
        )
    ]

    assert definitions == [COMPONENT_ROOTS["common"] / "json.py"]


def test_coverage_tree_normalizes_source_paths() -> None:
    """Keep report grouping aligned with paths emitted by coverage.py."""
    source = (REPOSITORY_ROOT / "scripts" / "coverage-tree.jq").read_text()

    assert 'sub("^(common|ci|server)/src/monori/"; "")' in source
    assert 'sub("^monori/"; "")' in source
    for path_rule in (
        "common/",
        "ci/lib/",
        "ci/quality_graph/",
        "^(ci|server)/tests/",
        "^server/(app|tests)/",
        "^ci/(lib|quality_graph|tests)/",
    ):
        assert path_rule in source


def test_python_tooling_is_split_into_explicit_ci_profiles() -> None:
    """Keep CI jobs from installing one aggregate development environment."""
    root = project(REPOSITORY_ROOT / "pyproject.toml")
    groups = section(root, "dependency-groups")

    assert "dev" not in groups
    assert {
        "ci",
        "format",
        "lint",
        "test",
        "type",
        "analyze",
        "audit",
        "mutation",
        "runtime",
    } <= groups.keys()
    ci_dependencies = array_value(groups.get("ci"), "ci dependency group")
    assert any(
        string_value(dependency, "ci dependency").startswith("PyYAML")
        for dependency in ci_dependencies
    )

    setup = (REPOSITORY_ROOT / ".github/actions/setup-project/action.yml").read_text()
    assert "python-profile:" in setup
    assert '--group "${{ inputs.python-profile }}"' in setup
    assert "--group dev" not in setup
    assert "--all-packages --group dev" not in setup
    assert "${{ inputs.python-profile }}-${{ hashFiles('uv.lock') }}" in setup
    assert 'echo "UV_NO_SYNC=1"' in setup


def test_clean_removes_the_current_ci_coverage_output() -> None:
    """Clean the coverage file at the path written by the current script."""
    makefile = (REPOSITORY_ROOT / "Makefile").read_text()

    assert "ci/coverage.json" in makefile
    assert "monori/ci/coverage.json" not in makefile
