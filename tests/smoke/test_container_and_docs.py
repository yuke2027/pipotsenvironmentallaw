"""Static checks for the container recipe and documented commands."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "docs" / "legacy"


@pytest.mark.smoke
def test_dockerfile_is_non_root_and_has_a_healthcheck() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER appuser" in text
    assert "HEALTHCHECK" in text
    assert "/api/v1/health" in text
    assert "fonts-noto-cjk" in text
    assert "python:3.10.16-slim-bookworm" in text
    assert "password=" not in text.lower()
    assert "JWT_SECRET=" not in text


@pytest.mark.smoke
def test_compose_declares_platform_volumes_and_health() -> None:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "platform:" in text
    assert "platform-db:" in text
    assert "platform-models:" in text
    assert "platform-exports:" in text
    assert "/api/v1/health" in text
    assert "JWT_SECRET" in text


@pytest.mark.smoke
def test_documented_cli_help_matches_the_parser() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    deployment = (ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")
    combined = readme + "\n" + deployment
    assert "不依赖外网" in combined or "不访问" in combined
    assert "python -m app.cli --help" in readme
    assert "python -m app.cli import-csv --help" in readme
    assert "platform" in deployment
    from app.legacy_cli import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "import-csv" in help_text
    assert "serve" in help_text


@pytest.mark.smoke
def test_platform_image_contains_the_online_acceptance_report() -> None:
    repository = ROOT.parents[1]
    dockerfile = (repository / "Dockerfile.platform").read_text(encoding="utf-8")
    assert "COPY scripts/online_acceptance_report.py ./scripts/online_acceptance_report.py" in dockerfile
    assert "COPY scripts/verify_acceptance.py ./scripts/verify_acceptance.py" in dockerfile
    assert (repository / "scripts" / "online_acceptance_report.py").is_file()


@pytest.mark.smoke
def test_acceptance_stack_initializes_isolated_schema_before_workers() -> None:
    repository = ROOT.parents[1]
    compose = (repository / "compose.acceptance.yml").read_text(encoding="utf-8")
    assert "acceptance-migrate:" in compose
    assert '"scripts.prepare_acceptance"' in compose
    assert compose.count("service_completed_successfully") >= 3
