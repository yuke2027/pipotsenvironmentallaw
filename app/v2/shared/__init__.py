"""Shared application contracts and infrastructure for the v2 platform."""

from .job_contracts import ArtifactRef, JobProgress, JobResult, JobSpec, JobState
from .repositories import Repository

__all__ = ["ArtifactRef", "JobProgress", "JobResult", "JobSpec", "JobState", "Repository"]
