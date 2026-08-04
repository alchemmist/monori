"""Protect the dependency direction and package layout of Monori's Python code."""

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[3]
PACKAGE_ROOT = REPOSITORY_ROOT / "monori"


def python_modules(root: Path) -> list[Path]:
    """Return all Python modules below a package directory."""
    return sorted(root.rglob("*.py"))


def parsed_imports(path: Path) -> list[ast.Import | ast.ImportFrom]:
    """Return import nodes from one Python module."""
    tree = ast.parse(path.read_text(), filename=str(path))
    return [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]


def test_root_project_owns_the_monori_package() -> None:
    """Keep every Python domain under the package built by the root project."""
    project = (REPOSITORY_ROOT / "pyproject.toml").read_text()

    assert 'name = "monori"' in project
    assert (PACKAGE_ROOT / "common").is_dir()
    assert (PACKAGE_ROOT / "ci").is_dir()
    assert (PACKAGE_ROOT / "server").is_dir()


def test_internal_imports_are_absolute_and_namespaced() -> None:
    """Reject relative imports and legacy top-level package names."""
    violations: list[str] = []
    for path in python_modules(PACKAGE_ROOT):
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
        for path in python_modules(PACKAGE_ROOT / "ci" / "lib")
        for imported in parsed_imports(path)
        if isinstance(imported, ast.ImportFrom)
        and (imported.module or "").startswith("monori.ci.quality_graph")
    ]

    assert violations == []


def test_json_value_has_one_definition() -> None:
    """Keep the recursive JSON type in the common package only."""
    definitions = [
        path
        for path in python_modules(PACKAGE_ROOT)
        if any(
            isinstance(node, ast.TypeAlias) and node.name.id == "JsonValue"
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path)))
        )
    ]

    assert definitions == [PACKAGE_ROOT / "common" / "json.py"]
