"""Health mapping. A version is reported only when it is activated and loaded."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelHealth:
    version: str | None
    loaded: bool


def health_payload(
    *,
    database_ok: bool,
    saits: ModelHealth | None,
    lstm: ModelHealth | None,
) -> dict[str, object]:
    """Map runtime state onto the public health document.

    Missing or unloaded models are reported as unavailable. The payload never
    invents a version string for a model that is not both recorded and loaded.
    """

    saits_version = _loaded_version(saits)
    lstm_version = _loaded_version(lstm)
    return {
        "service": "ok",
        "database": "ok" if database_ok else "unavailable",
        "models": {"saits": saits_version, "lstm": lstm_version},
        "imputation_available": saits_version is not None or lstm_version is not None,
    }


def _loaded_version(model: ModelHealth | None) -> str | None:
    if model is None or not model.loaded or not model.version:
        return None
    return model.version
