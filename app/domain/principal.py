"""Authenticated caller carried between the token gate and services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Principal:
    user_id: int
    username: str
    role: str
    password_change_required: bool
    jti: str
    expires_at: datetime
