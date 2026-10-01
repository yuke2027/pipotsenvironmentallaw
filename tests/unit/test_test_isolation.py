"""Tests for repository-level test isolation."""

from __future__ import annotations

import socket

import pytest


@pytest.mark.unit
def test_real_socket_connections_are_blocked() -> None:
    """The autouse fixture rejects accidental network access."""
    with pytest.raises(AssertionError, match="Real socket access is blocked"):
        socket.create_connection(("example.com", 443), timeout=0.1)
