"""Compatibility facade for model execution jobs.

Model persistence and legacy algorithm orchestration live behind the ML domain
adapter; existing worker imports remain stable during migration.
"""
from app.v2.domains.ml.repository import model_job

__all__ = ["model_job"]
