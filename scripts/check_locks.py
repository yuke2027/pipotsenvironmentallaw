"""Verify that dependency manifests and lock files remain reproducible."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PINNED_REQUIREMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*==[^\s;]+$")


def requirement_lines(path: Path) -> list[str]:
    """Return non-comment requirement lines from *path*."""
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def validate(path: Path) -> list[str]:
    """Return manifest validation failures without invoking a package index."""
    failures: list[str] = []
    for line in requirement_lines(path):
        if line.startswith("-r "):
            continue
        if not PINNED_REQUIREMENT.fullmatch(line):
            failures.append(f"{path.name}: unpinned requirement {line!r}")
    return failures


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    runtime = root / "requirements.txt"
    test = root / "requirements-test.txt"
    runtime_lock = root / "requirements.lock"
    platform_lock = root / "requirements-platform.lock"
    test_lock = root / "requirements-test.lock"

    runtime_lines = requirement_lines(runtime)
    test_lines = [line for line in requirement_lines(test) if not line.startswith("-r ")]
    failures = [*validate(runtime), *validate(test)]
    if requirement_lines(runtime_lock) != runtime_lines:
        failures.append("requirements.lock does not exactly match requirements.txt")
    platform_lines = requirement_lines(platform_lock)
    if requirement_lines(test_lock) != [*platform_lines, *test_lines]:
        failures.append(
            "requirements-test.lock does not contain the exact platform and test dependency set"
        )

    if failures:
        print("\n".join(failures))
        return 1
    print("Dependency manifests and lock inputs are fully pinned and synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
