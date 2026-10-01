"""Logging helpers that prevent secrets from reaching log sinks or audit data."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_LABEL = (
    r"(?:password|token|authorization|"
    r"smtp(?:[\s_.-]*(?:password|token|secret))?|"
    r"webhook(?:[\s_.-]*(?:password|token|secret))?)"
)
_SECRET_IN_TEXT = re.compile(
    rf"(?P<key>\b{_SENSITIVE_LABEL}\b)"
    r"(?P<separator>\s*(?:=|:)\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;\]\)}}]+)",
    re.IGNORECASE,
)


def is_sensitive_key(key: object) -> bool:
    """Return whether a mapping key names a value that must not be logged."""
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    if any(term in normalized for term in ("password", "token", "authorization")):
        return True
    return ("smtp" in normalized or "webhook" in normalized) and "secret" in normalized


def sanitize_text(value: str) -> str:
    """Redact supported secret assignments embedded in unstructured text."""

    def redact(match: re.Match[str]) -> str:
        return f"{match.group('key')}{match.group('separator')}{REDACTED}"

    return _SECRET_IN_TEXT.sub(redact, value)


def sanitize_value(value: Any) -> Any:
    """Return a recursively sanitized copy suitable for logs, audits, or errors.

    Mapping values are redacted based on their key, while strings and exception
    messages are inspected for secret assignments that may appear in text.
    """
    if isinstance(value, Mapping):
        return {
            key: REDACTED if is_sensitive_key(key) else sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_value(item) for item in value)
    if isinstance(value, set):
        return {sanitize_value(item) for item in value}
    if isinstance(value, BaseException):
        return sanitize_text(str(value))
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def sanitize_audit_details(details: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize structured audit details before they are persisted or emitted."""
    sanitized = sanitize_value(details)
    return dict(sanitized)


class SensitiveDataFilter(logging.Filter):
    """A logging filter that redacts messages, exceptions, and structured extras."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered_message = record.getMessage()
        except Exception:  # pragma: no cover - defensive logging path
            rendered_message = str(record.msg)

        record.msg = sanitize_text(rendered_message)
        record.args = ()

        if record.exc_info is not None:
            exception = record.exc_info[1]
            record.exc_info = None
            record.exc_text = (
                f"{type(exception).__name__}: {sanitize_value(exception)}"
                if exception is not None
                else None
            )

        for key, value in tuple(record.__dict__.items()):
            if key in {"msg", "args", "exc_info", "exc_text"}:
                continue
            record.__dict__[key] = sanitize_value(value)
        if record.exc_text is not None:
            record.exc_text = sanitize_text(record.exc_text)
        return True


def install_sensitive_data_filter(logger: logging.Logger | None = None) -> SensitiveDataFilter:
    """Install and return one redaction filter on a logger and its handlers."""
    target = logger or logging.getLogger()
    existing = next(
        (item for item in target.filters if isinstance(item, SensitiveDataFilter)), None
    )
    data_filter = existing if isinstance(existing, SensitiveDataFilter) else SensitiveDataFilter()
    if existing is None:
        target.addFilter(data_filter)

    for handler in target.handlers:
        if not any(isinstance(item, SensitiveDataFilter) for item in handler.filters):
            handler.addFilter(data_filter)
    return data_filter
