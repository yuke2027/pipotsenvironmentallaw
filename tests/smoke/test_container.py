"""Task 16.5: image runs as non-root, resolves Noto CJK, and persists volumes.

Uses throwaway containers and a temporary volume only; a running compose stack is
never restarted. Skipped when Docker or the locally built image is unavailable.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Iterator

import pytest

IMAGE = "environmental-platform-api:local"


def _docker(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False, encoding="utf-8"
    )


def _available() -> bool:
    if shutil.which("docker") is None:
        return False
    info = _docker("image", "inspect", IMAGE, timeout=30)
    return info.returncode == 0


pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not _available(), reason="docker or the local platform image is unavailable"),
]


def _run(*args: str, volume: str | None = None, script: str) -> subprocess.CompletedProcess[str]:
    command = ["run", "--rm", "--network", "none", "--entrypoint", "sh"]
    if volume is not None:
        command += ["-v", f"{volume}:/workspace/var/platform"]
    return _docker(*command, *args, IMAGE, "-c", script)


@pytest.fixture
def volume() -> Iterator[str]:
    name = f"esp-smoke-{uuid.uuid4().hex[:12]}"
    assert _docker("volume", "create", name).returncode == 0
    try:
        yield name
    finally:
        _docker("volume", "rm", "-f", name)


def test_process_runs_as_a_non_root_user() -> None:
    result = _run(script="id -u; id -un")
    assert result.returncode == 0, result.stderr
    uid, user = result.stdout.split()
    assert uid != "0" and user != "root"


def test_image_resolves_a_cjk_font_without_network() -> None:
    result = _run(script="fc-list :lang=zh family | head -1")
    assert result.returncode == 0, result.stderr
    assert any(token in result.stdout for token in ("Noto", "WenQuanYi", "CJK"))


def test_no_secret_is_baked_into_the_image_environment() -> None:
    config = _docker("image", "inspect", IMAGE, "--format", "{{json .Config.Env}}")
    assert config.returncode == 0
    lowered = config.stdout.lower()
    for marker in ("password=", "secret_key=", "jwt_secret=", "esp_secret"):
        assert marker not in lowered


def test_volume_contents_survive_container_recreation(volume: str) -> None:
    write = _run(volume=volume, script="echo persisted > /workspace/var/platform/marker.txt && sync")
    assert write.returncode == 0, write.stderr
    read = _run(volume=volume, script="cat /workspace/var/platform/marker.txt")
    assert read.returncode == 0, read.stderr
    assert read.stdout.strip() == "persisted"


def test_volume_is_writable_by_the_non_root_user(volume: str) -> None:
    result = _run(volume=volume, script="touch /workspace/var/platform/ok && echo yes")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "yes"


def test_application_package_starts_without_network_or_secrets() -> None:
    result = _run(script="python -c \"import app.v2.main as m; print(callable(m.create_app))\"")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"
