"""Application use cases for monitoring read models."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class StationFilter:
    city_id: str | None = None


@dataclass(frozen=True)
class ObservationFilter:
    start: Any = None
    end: Any = None
    station_id: str | None = None
    pollutant: str | None = None
    city_id: str | None = None
    page_number: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class StationDetailFilter:
    station_id: str


@dataclass(frozen=True)
class EvaluationFilter:
    start: Any = None
    end: Any = None
    city_id: str | None = None
    station_id: str | None = None
    pollutant: str | None = None
    status: str | None = None
    page_number: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class QualityFilter:
    start: Any = None
    end: Any = None
    city_id: str | None = None


@dataclass(frozen=True)
class AqiFilter:
    station_id: str
    start: Any
    end: Any


@dataclass(frozen=True)
class ForecastFilter:
    station_id: str
    pollutant: str = "PM2.5"
    job_id: str | None = None


@dataclass(frozen=True)
class ImputationFilter:
    station_id: str
    start: Any
    end: Any
    pollutant: str = "PM2.5"


@dataclass(frozen=True)
class TimeseriesFilter:
    start: Any
    end: Any
    pollutant: str
    station_ids: tuple[str, ...] = ()
    city_id: str | None = None
    resolution: str = "hour"


@dataclass(frozen=True)
class DashboardFilter:
    city_id: str | None = None
    start: Any = None
    end: Any = None
    enforcement_user_id: str | None = None
    include_pending: bool = True


class MonitoringReadPort(Protocol):
    def cities(self) -> dict[str, Any]: ...

    def stations(self, filters: StationFilter) -> dict[str, Any]: ...

    def observations(self, filters: ObservationFilter) -> dict[str, Any]: ...

    def station_detail(self, filters: StationDetailFilter) -> dict[str, Any] | None: ...

    def evaluations(self, filters: EvaluationFilter) -> dict[str, Any]: ...

    def quality(self, filters: QualityFilter, license_confirmed: bool) -> dict[str, Any]: ...

    def aqi(self, filters: AqiFilter) -> dict[str, Any]: ...

    def forecasts(self, filters: ForecastFilter) -> dict[str, Any]: ...

    def imputations(self, filters: ImputationFilter) -> dict[str, Any]: ...

    def timeseries(self, filters: TimeseriesFilter) -> dict[str, Any]: ...

    def dashboard(self, filters: DashboardFilter) -> dict[str, Any]: ...


class MonitoringService:
    """Coordinate monitoring use cases without depending on a web framework."""

    def __init__(self, read_port: MonitoringReadPort):
        self.read_port = read_port

    def list_cities(self) -> dict[str, Any]:
        return self.read_port.cities()

    def list_stations(self, filters: StationFilter) -> dict[str, Any]:
        return self.read_port.stations(filters)

    def list_observations(self, filters: ObservationFilter) -> dict[str, Any]:
        return self.read_port.observations(filters)

    def get_station_detail(self, filters: StationDetailFilter) -> dict[str, Any] | None:
        return self.read_port.station_detail(filters)

    def list_evaluations(self, filters: EvaluationFilter) -> dict[str, Any]:
        return self.read_port.evaluations(filters)

    def get_quality(self, filters: QualityFilter, license_confirmed: bool) -> dict[str, Any]:
        return self.read_port.quality(filters, license_confirmed)

    def list_aqi(self, filters: AqiFilter) -> dict[str, Any]:
        return self.read_port.aqi(filters)

    def list_forecasts(self, filters: ForecastFilter) -> dict[str, Any]:
        return self.read_port.forecasts(filters)

    def list_imputations(self, filters: ImputationFilter) -> dict[str, Any]:
        return self.read_port.imputations(filters)

    def get_timeseries(self, filters: TimeseriesFilter) -> dict[str, Any]:
        return self.read_port.timeseries(filters)

    def get_dashboard(self, filters: DashboardFilter) -> dict[str, Any]:
        return self.read_port.dashboard(filters)
