"""Atomic model activation. A failed check leaves both the pointer and the handle."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivationState:
    db_id: int | None
    memory_id: int | None


_STAGES = ("checksum", "manifest", "shape", "inference")


def activate_model(
    current: ActivationState,
    candidate_id: int,
    stages: dict[str, bool],
) -> ActivationState:
    """Switch the database pointer and memory handle together, or not at all."""

    if any(stage not in stages for stage in _STAGES):
        return current
    if all(stages[stage] for stage in _STAGES):
        return ActivationState(db_id=candidate_id, memory_id=candidate_id)
    return current
