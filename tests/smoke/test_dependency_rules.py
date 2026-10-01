"""Static architecture guards for application and legacy dependency boundaries."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parents[2]
APP_ROOT = PROJECT_ROOT / "app"
LEGACY_ROOT = PROJECT_ROOT / "legacy_algorithms"
LEGACY_TOP_LEVEL_MODULES = {
    "data_preprocessing",
    "data_imputation",
    "train_all_models",
    "legal_supervision",
}
ORM_MODULE_PREFIXES = ("sqlalchemy", "sqlmodel", "peewee", "tortoise")


def _imports_in(path: Path) -> Iterable[tuple[int, str]]:
    """Yield imported module names and source lines from one Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from ((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.lineno, node.module


def _python_files(root: Path) -> Iterable[Path]:
    return root.rglob("*.py") if root.exists() else ()


def _matches_prefix(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


@pytest.mark.smoke
def test_services_do_not_import_orm_modules() -> None:
    """Services must depend on repository abstractions, not ORM implementations."""
    violations = [
        f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}"
        for path in _python_files(APP_ROOT / "services")
        for line, module in _imports_in(path)
        if _matches_prefix(module, ORM_MODULE_PREFIXES)
    ]
    assert not violations, "app/services must not import ORM modules:\n" + "\n".join(violations)


@pytest.mark.smoke
def test_legacy_algorithms_do_not_import_app_database() -> None:
    """Legacy algorithms remain database-independent DataFrame/array code."""
    violations = [
        f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}"
        for path in _python_files(LEGACY_ROOT)
        for line, module in _imports_in(path)
        if module == "app.db" or module.startswith("app.db.")
    ]
    assert not violations, "legacy_algorithms must not import app.db:\n" + "\n".join(violations)


@pytest.mark.smoke
def test_application_uses_legacy_algorithms_only_via_legacy_adapter() -> None:
    """Only app/adapters/legacy may import the canonical legacy package."""
    legacy_adapter_root = APP_ROOT / "adapters" / "legacy"
    violations = [
        f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}"
        for path in _python_files(APP_ROOT)
        if legacy_adapter_root not in path.parents
        for line, module in _imports_in(path)
        if module.split(".", 1)[0] == "legacy_algorithms"
        or module.split(".", 1)[0] in LEGACY_TOP_LEVEL_MODULES
    ]
    assert not violations, (
        "app must import legacy algorithms only through app/adapters/legacy:\n"
        + "\n".join(violations)
    )
