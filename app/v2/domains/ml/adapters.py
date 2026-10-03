"""Compatibility adapters for the existing model algorithms."""

from typing import Any


class LegacyModelExecutionAdapter:
    def execute(self, db: Any, store: Any, settings: Any, job: Any, progress: Any) -> dict[str, Any]:
        from app.v2.domains.ml.repository import model_job

        return model_job(db, store, settings, job, progress)
