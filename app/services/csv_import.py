"""Directory import of legacy wide tables. Bad files are isolated and counted."""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from app.adapters.legacy.preprocessing import preprocess_wide_dataframe
from app.adapters.providers.csv_fallback import rows_from_particulate
from app.domain.dataframe_contracts import AlgorithmContractError
from app.domain.records import MonitoringDraft
from app.domain.repositories import MonitoringRepository
from app.services.collection import ingest

_REQUIRED = frozenset({"date", "hour", "type"})
_SHANGHAI = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class FileImportResult:
    name: str
    inserted: int
    skipped: int
    invalid: int
    missing_columns: tuple[str, ...] = ()
    extra_columns: tuple[str, ...] = ()
    error: str | None = None


@dataclass
class ImportReport:
    files: list[FileImportResult] = field(default_factory=list)

    @property
    def files_seen(self) -> int:
        return len(self.files)

    @property
    def inserted(self) -> int:
        return sum(item.inserted for item in self.files)

    @property
    def skipped(self) -> int:
        return sum(item.skipped for item in self.files)

    @property
    def invalid(self) -> int:
        return sum(item.invalid for item in self.files)


class CsvImporter:
    def __init__(
        self,
        monitoring: MonitoringRepository,
        resolve_station: dict[str, int],
    ) -> None:
        self._monitoring = monitoring
        self._stations = dict(resolve_station)

    def import_directory(
        self,
        directory: Path,
        *,
        allowed_stations: set[str] | None = None,
    ) -> ImportReport:
        report = ImportReport()
        if not directory.is_dir():
            return report
        for path in sorted(directory.glob("*.csv")):
            report.files.append(self._import_file(path, allowed_stations))
        return report

    def _import_file(self, path: Path, allowed_stations: set[str] | None) -> FileImportResult:
        try:
            frame = pd.read_csv(path)
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            return FileImportResult(path.name, 0, 0, 0, error=type(exc).__name__)
        columns = {str(column) for column in frame.columns}
        missing = tuple(sorted(_REQUIRED - columns))
        extra: tuple[str, ...] = ()
        if allowed_stations is not None:
            extra = tuple(sorted(columns - _REQUIRED - allowed_stations))
        if missing or extra:
            return FileImportResult(
                path.name,
                0,
                0,
                0,
                missing_columns=missing,
                extra_columns=extra,
                error="column mismatch",
            )
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                converted = preprocess_wide_dataframe(frame)
        except (AlgorithmContractError, ValueError, OSError) as exc:
            return FileImportResult(path.name, 0, 0, 0, error=type(exc).__name__)
        drafts: list[MonitoringDraft] = []
        invalid = 0
        for dated in converted.particulate.values():
            for observation in rows_from_particulate(dated):
                station_id = self._stations.get(observation.station_code)
                if station_id is None or observation.observed_at.tzinfo is None:
                    invalid += 1
                    continue
                if any(
                    value is not None and (value < 0 or value != value)
                    for value in (observation.pm25, observation.pm10, observation.aqi)
                ):
                    invalid += 1
                    continue
                drafts.append(
                    MonitoringDraft(
                        station_id=station_id,
                        observed_at=observation.observed_at.astimezone(timezone.utc),
                        pm25=observation.pm25,
                        pm10=observation.pm10,
                        aqi=observation.aqi,
                        source="CSV",
                        is_imputed=False,
                    )
                )
        outcome = ingest(drafts, self._monitoring, source="CSV")
        return FileImportResult(
            path.name,
            outcome.counts.inserted,
            outcome.counts.skipped,
            outcome.counts.invalid + invalid,
        )


def shanghai_hour(local_date: str, hour: int) -> datetime:
    """Build an aware instant for a Shanghai local hour."""

    local = datetime.fromisoformat(f"{local_date}T{hour:02d}:00:00").replace(tzinfo=_SHANGHAI)
    return local.astimezone(timezone.utc)
