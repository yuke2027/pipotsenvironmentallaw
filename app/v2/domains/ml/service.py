"""Application service boundary for model training and inference jobs."""

from typing import Any, Protocol


class ModelExecutionPort(Protocol):
    def execute(self, db: Any, store: Any, settings: Any, job: Any, progress: Any) -> dict[str, Any]: ...


class ModelExecutionService:
    """Run model jobs through an adapter while keeping task orchestration stable."""

    def __init__(self, port: ModelExecutionPort):
        self.port = port

    def execute(self, db: Any, store: Any, settings: Any, job: Any, progress: Any) -> dict[str, Any]:
        return self.port.execute(db, store, settings, job, progress)
