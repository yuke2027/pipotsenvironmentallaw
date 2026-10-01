"""Resolved filesystem locations derived exclusively from :mod:`app.core.config`."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .config import Settings, get_settings


@dataclass(frozen=True)
class PathSettings:
    """Absolute, centrally resolved platform paths.

    Application code should use the typed directory attributes and helper
    methods here rather than combining relative path fragments itself.
    Relative configuration values are rooted at ``project_root``; values that
    would escape it are rejected. Absolute values remain supported for mounted
    volumes and externally managed deployment locations.
    """

    project_root: Path
    data_dir: Path
    model_dir: Path
    export_dir: Path
    local_config_dir: Path
    database_path: Path

    @classmethod
    def from_settings(cls, settings: Settings) -> "PathSettings":
        root = settings.project_root.expanduser().resolve()
        return cls(
            project_root=root,
            data_dir=cls._resolve_configured(root, settings.data_dir),
            model_dir=cls._resolve_configured(root, settings.model_dir),
            export_dir=cls._resolve_configured(root, settings.export_dir),
            local_config_dir=cls._resolve_configured(root, settings.local_config_dir),
            database_path=cls._resolve_configured(root, settings.database_path),
        )

    @staticmethod
    def _resolve_configured(project_root: Path, configured_path: Path) -> Path:
        candidate = configured_path.expanduser()
        if candidate.is_absolute():
            return candidate.resolve()

        resolved = (project_root / candidate).resolve()
        try:
            resolved.relative_to(project_root)
        except ValueError as error:
            raise ValueError(
                f"relative path escapes project_root: {configured_path}"
            ) from error
        return resolved

    def ensure_directories(self) -> None:
        """Create configured runtime directories without touching legacy paths."""
        for directory in (
            self.data_dir,
            self.model_dir,
            self.export_dir,
            self.local_config_dir,
            self.database_path.parent,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def database_url(self) -> str:
        """Build the default SQLite URL from the centrally resolved DB path."""
        return f"sqlite:///{self.database_path.as_posix()}"

    def data_path(self, *parts: str | Path) -> Path:
        """Resolve a safe child path below the configured data directory."""
        return self._child_path(self.data_dir, parts)

    def model_path(self, *parts: str | Path) -> Path:
        """Resolve a safe child path below the configured model directory."""
        return self._child_path(self.model_dir, parts)

    def export_path(self, *parts: str | Path) -> Path:
        """Resolve a safe child path below the configured export directory."""
        return self._child_path(self.export_dir, parts)

    @staticmethod
    def _child_path(directory: Path, parts: Iterable[str | Path]) -> Path:
        candidate = directory.joinpath(*parts).resolve()
        try:
            candidate.relative_to(directory)
        except ValueError as error:
            raise ValueError(f"path escapes configured directory: {candidate}") from error
        return candidate


@lru_cache(maxsize=1)
def get_paths() -> PathSettings:
    """Return the process-wide resolved paths for the validated settings."""
    return PathSettings.from_settings(get_settings())


def reset_paths_cache() -> None:
    """Clear cached paths for controlled test or process reconfiguration."""
    get_paths.cache_clear()
