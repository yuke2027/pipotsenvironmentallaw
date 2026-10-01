"""Import-boundary smoke tests for the initial package skeleton."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.smoke
def test_initial_packages_and_entry_point_import() -> None:
    app = importlib.import_module("app")
    main = importlib.import_module("app.main")
    legacy = importlib.import_module("legacy_algorithms")

    assert app.__version__ == "0.1.0"
    assert main.application_name() == "environmental-supervision-platform"
    assert legacy.__doc__ is not None
