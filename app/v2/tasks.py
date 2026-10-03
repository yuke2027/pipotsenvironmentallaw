"""Compatibility facade for the Celery job worker.

The worker lifecycle and dispatch implementation lives in the jobs domain.
The public Celery import path is preserved for Compose and existing operators.
"""
from app.v2.domains.jobs.worker import celery_app, dispatch, execute_job, run_job

__all__ = ["celery_app", "dispatch", "execute_job", "run_job"]
