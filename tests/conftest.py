"""Shared test isolation safeguards."""

from __future__ import annotations

import os
import ipaddress
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import settings

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PRODUCTION_DATABASES = (
    _PROJECT_ROOT / "var" / "environmental_supervision.db",
    _PROJECT_ROOT / "environmental_supervision.db",
)


settings.register_profile("platform", max_examples=100, deadline=None)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "platform"))


@pytest.fixture(autouse=True)
def block_unmocked_socket(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail fast when a test attempts a real network connection.

    Tests that exercise HTTP behavior must use ``httpx.MockTransport`` or an
    explicit fake adapter, so no test can silently reach an external service.
    """

    def blocked_socket(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "Real socket access is blocked in tests; use MockTransport or a fake adapter."
        )

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    def local_connect(sock, address):
        # Windows asyncio creates its wakeup socket pair over loopback.
        if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
            return original_connect(sock, address)
        return blocked_socket()
    def local_connect_ex(sock, address):
        if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
            return original_connect_ex(sock, address)
        return blocked_socket()
    monkeypatch.setattr(socket, "create_connection", blocked_socket)
    monkeypatch.setattr(socket.socket, "connect", local_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", local_connect_ex)
    yield


def _database_fingerprint(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


@pytest.fixture(autouse=True)
def production_database_is_untouched() -> Iterator[None]:
    """Database tests must use tmp_path and leave the default SQLite file alone."""

    before = {path: _database_fingerprint(path) for path in _PRODUCTION_DATABASES}
    yield
    after = {path: _database_fingerprint(path) for path in _PRODUCTION_DATABASES}
    assert after == before
