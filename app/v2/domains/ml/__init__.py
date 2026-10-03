"""Machine-learning domain compatibility facade."""

from app.v2.domains.ml.service import ModelExecutionService

__all__ = ["ModelExecutionService", "model_job"]


def __getattr__(name: str) -> object:
    if name == "model_job":
        from app.v2.ml import model_job

        return model_job
    raise AttributeError(name)
