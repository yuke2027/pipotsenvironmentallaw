"""Alert payload shared by email and webhook. Credentials never enter the body."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

REQUIRED_FIELDS: tuple[str, ...] = ("城市", "站点", "污染物", "统计值", "限值", "倍数", "等级")
_FORBIDDEN_TOKENS = ("credential", "token", "secret")


@dataclass(frozen=True)
class AlertPayload:
    city: str
    station: str
    pollutant: str
    statistic: str
    limit: str
    ratio: str
    level: str

    def as_mapping(self) -> dict[str, str]:
        return {
            "城市": self.city,
            "站点": self.station,
            "污染物": self.pollutant,
            "统计值": self.statistic,
            "限值": self.limit,
            "倍数": self.ratio,
            "等级": self.level,
        }


def render_email(payload: AlertPayload) -> tuple[str, str]:
    """Return a Chinese subject and body containing the seven business fields."""

    fields = payload.as_mapping()
    body = "\n".join(f"{name}：{value}" for name, value in fields.items())
    return f"空气质量告警：{payload.city}{payload.station}", body


class Notifier(Protocol):
    def deliver(self, payload: AlertPayload) -> None: ...


def payload_contains_secret(rendered: str, secret: str | None) -> bool:
    """True when rendered text contains a credential marker or the secret value."""

    lowered = rendered.lower()
    if any(token in lowered for token in _FORBIDDEN_TOKENS):
        return True
    if secret is None or secret == "":
        return False
    return secret in rendered
