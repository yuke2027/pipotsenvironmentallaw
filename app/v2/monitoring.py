from typing import Any

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from app.v2.shared.http_errors import ErrorCode
from app.v2.auth import get_user
from app.v2.common import UNITS, fail
from app.v2.domains.auth.models import User
from app.v2.contracts import Page, CityView, StationView, ObservationView, EvaluationView
from app.v2.domains.monitoring.repository import SqlAlchemyMonitoringReadPort
from app.v2.domains.monitoring.service import (
    AqiFilter,
    DashboardFilter,
    EvaluationFilter,
    ForecastFilter,
    ImputationFilter,
    MonitoringService,
    ObservationFilter,
    QualityFilter,
    StationDetailFilter,
    StationFilter,
    TimeseriesFilter,
)

router = APIRouter(tags=["监测与评价"], dependencies=[Depends(get_user)])


@router.get("/cities", response_model=Page[CityView])
def cities(request: Request) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return MonitoringService(SqlAlchemyMonitoringReadPort(session)).list_cities()


@router.get("/stations", response_model=Page[StationView])
def stations(request: Request, city_id: str | None = None) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return MonitoringService(SqlAlchemyMonitoringReadPort(session)).list_stations(StationFilter(city_id))


@router.get("/stations/{station_id}", response_model=StationView)
def station_detail(station_id: str, request: Request) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        item = MonitoringService(SqlAlchemyMonitoringReadPort(session)).get_station_detail(
            StationDetailFilter(station_id)
        )
        if item is None:
            fail("站点不存在", ErrorCode.NOT_FOUND)
        return item

@router.get("/observations", response_model=Page[ObservationView])
def observations(request: Request, start: date | None = None, end: date | None = None,
                 station_id: str | None = None, pollutant: str | None = None, city_id: str | None = None,
                 page_number: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
    if start and end and (end < start or (end - start).days > 731):
        fail("查询时间顺序错误或超过两年", ErrorCode.INVALID_TIME_RANGE)
    with request.app.state.db.sessions() as session:
        return MonitoringService(SqlAlchemyMonitoringReadPort(session)).list_observations(
            ObservationFilter(start=start, end=end, station_id=station_id, pollutant=pollutant,
                              city_id=city_id, page_number=page_number, page_size=page_size))


@router.get("/timeseries")
def timeseries(request: Request, start: date, end: date, pollutant: str = "PM2.5",
               station_ids: str = "", city_id: str | None = None, resolution: str = "hour") -> dict[str, Any]:
    if start and end and (end < start or (end - start).days > 731):
        fail("查询时间顺序错误或超过两年", ErrorCode.INVALID_TIME_RANGE)
    if resolution not in {"hour", "day"}:
        fail("分辨率只能是 hour 或 day")
    ids = tuple(value for value in station_ids.split(",") if value)
    if len(ids) > 5:
        fail("最多同时查询 5 个站点")
    with request.app.state.db.sessions() as session:
        result = MonitoringService(SqlAlchemyMonitoringReadPort(session)).get_timeseries(
            TimeseriesFilter(start=start, end=end, pollutant=pollutant, station_ids=ids,
                             city_id=city_id, resolution=resolution)
        )
    if result.pop("_too_many", False):
        fail("查询结果过大，请缩短日期范围或减少站点数量")
    return result

@router.get("/dashboard")
def dashboard(request: Request, city_id: str | None = None, start: date | None = None,
              end: date | None = None, user: User = Depends(get_user)) -> dict[str, Any]:
    if start and end and (end < start or (end - start).days > 731):
        fail("查询时间顺序错误或超过两年", ErrorCode.INVALID_TIME_RANGE)
    with request.app.state.db.sessions() as session:
        enforcement_user_id = user.id if user.role == '执法人员' else None
        include_pending = user.role != '研究者'
        result = MonitoringService(SqlAlchemyMonitoringReadPort(session)).get_dashboard(
            DashboardFilter(city_id=city_id, start=start, end=end,
                            enforcement_user_id=enforcement_user_id, include_pending=include_pending)
        )
    if result.pop("_invalid_range", False):
        fail("查询时间顺序错误或超过两年", ErrorCode.INVALID_TIME_RANGE)
    return result

@router.get("/data-quality")
def quality(request: Request, start: date | None = None, end: date | None = None, city_id: str | None = None) -> dict[str, Any]:
    if start and end and (end < start or (end - start).days > 731):
        fail("查询时间顺序错误或超过两年", ErrorCode.INVALID_TIME_RANGE)
    with request.app.state.db.sessions() as session:
        return MonitoringService(SqlAlchemyMonitoringReadPort(session)).get_quality(
            QualityFilter(start=start, end=end, city_id=city_id),
            request.app.state.settings.source_license_ready(),
        )

@router.get("/evaluations", response_model=Page[EvaluationView])
def evaluations(request: Request, start: date | None = None, end: date | None = None,
                city_id: str | None = None,
                station_id: str | None = None, pollutant: str | None = None, status: str | None = None,
                page_number: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
    if start and end and end < start: fail("开始日期晚于结束日期")
    with request.app.state.db.sessions() as session:
        return MonitoringService(SqlAlchemyMonitoringReadPort(session)).list_evaluations(
            EvaluationFilter(start=start, end=end, city_id=city_id, station_id=station_id,
                             pollutant=pollutant, status=status,
                             page_number=page_number, page_size=page_size)
        )

@router.get("/aqi")
def aqi(request: Request, station_id: str, start: date, end: date) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return MonitoringService(SqlAlchemyMonitoringReadPort(session)).list_aqi(
            AqiFilter(station_id=station_id, start=start, end=end)
        )

@router.get("/forecasts")
def forecasts(request: Request, station_id: str, pollutant: str = "PM2.5", job_id: str | None = None) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        result = MonitoringService(SqlAlchemyMonitoringReadPort(session)).list_forecasts(
            ForecastFilter(station_id=station_id, pollutant=pollutant, job_id=job_id)
        )
        result["unit"] = UNITS.get(pollutant)
        return result

@router.get("/imputations")
def imputations(request: Request, station_id: str, start: date, end: date, pollutant: str = "PM2.5") -> dict[str, Any]:
    if end < start or (end-start).days > 365: fail("插补结果查询范围应在一年以内")
    with request.app.state.db.sessions() as session:
        return MonitoringService(SqlAlchemyMonitoringReadPort(session)).list_imputations(
            ImputationFilter(station_id=station_id, start=start, end=end, pollutant=pollutant)
        )
