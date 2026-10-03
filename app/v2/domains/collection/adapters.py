"""Adapters isolating the existing collection implementation during migration."""

from datetime import date
from typing import Any

from app.v2.domains.collection.repository import collect_range, import_file


class LegacyCollectionAdapter:
    def __init__(self, db: Any, store: Any, configuration: Any) -> None:
        self.db, self.store, self.configuration = db, store, configuration

    def collect(self, start: date, end: date, job_id: str, progress: Any) -> dict[str, Any]:
        return collect_range(self.db, self.store, self.configuration, start, end, job_id, progress)

    def import_file(self, content: bytes, kind: str) -> dict[str, Any]:
        return import_file(self.db, self.store, content, kind)
