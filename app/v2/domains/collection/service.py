"""Collection application port and legacy compatibility adapter boundary."""

from datetime import date
from typing import Any, Protocol


class CollectionPort(Protocol):
    def collect(self, start: date, end: date, job_id: str, progress: Any) -> dict[str, Any]: ...

    def import_file(self, content: bytes, kind: str) -> dict[str, Any]: ...


class CollectionService:
    def __init__(self, port: CollectionPort) -> None:
        self.port = port

    def collect(self, start: date, end: date, job_id: str, progress: Any) -> dict[str, Any]:
        return self.port.collect(start, end, job_id, progress)

    def import_file(self, content: bytes, kind: str) -> dict[str, Any]:
        return self.port.import_file(content, kind)
