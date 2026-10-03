"""Compatibility facade for append-only platform backups."""
from app.v2.shared.backup_repository import archive_files, file_manifest

__all__ = ["archive_files", "file_manifest"]
