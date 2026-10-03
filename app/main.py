"""Default production entry; legacy factory remains in app.legacy_main."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from app.v2.config import Settings

def application_name() -> str:
    return "environmental-supervision-platform"

def create_app(settings: "Settings | None" = None) -> "FastAPI":
    from app.v2.main import create_app as create_platform
    return create_platform(settings)
