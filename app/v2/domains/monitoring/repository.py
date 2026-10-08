"""SQLAlchemy read adapter for monitoring endpoints."""

from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from app.v2.common import UNITS, page, serialize
from app.v2.domains.collection.models import SourceAttempt, SourceFile
from app.v2.domains.enforcement.models import Inspection
from app.v2.domains.ml.models import DerivedValue
from app.v2.domains.monitoring.models import AQIResult, City, Evaluation, Observation, Station
from app.v2.domains.monitoring.service import (
    AqiFilter,
    EvaluationFilter,
    ForecastFilter,
    ImputationFilter,
    ObservationFilter,
    DashboardFilter,
    QualityFilter,
    StationDetailFilter,
    StationFilter,
    TimeseriesFilter,
)
from app.v2.domains.collection.repository import LOCAL
from datetime import datetime, timedelta, timezone


class SqlAlchemyMonitoringReadPort:
    def __init__(self, session: Session) -> None:
        self.session = session

    def cities(self) -> dict[str, Any]:
        return page(self.session, select(City).order_by(City.name), 1, 100)

    def stations(self, filters: StationFilter) -> dict[str, Any]:
        statement = select(Station).order_by(Station.name)
        if filters.city_id:
            statement = statement.where(Station.city_id == filters.city_id)
        return page(self.session, statement, 1, 1000)

    def observations(self, filters: ObservationFilter) -> dict[str, Any]:
        statement = (select(Observation).join(SourceFile).join(
            Station, Observation.station_id == Station.id
        ).where(SourceFile.is_current.is_(True), Observation.basis == (
            "source_aqi" if filters.pollutant == "AQI" else "hourly"
        )))
        if filters.start:
            statement = statement.where(Observation.local_date >= filters.start)
        if filters.end:
            statement = statement.where(Observation.local_date <= filters.end)
        if filters.station_id:
            statement = statement.where(Observation.station_id == filters.station_id)
        if filters.city_id:
            statement = statement.where(Station.city_id == filters.city_id)
        if filters.pollutant:
            statement = statement.where(Observation.pollutant == filters.pollutant)
        result = page(self.session, statement.order_by(Observation.observed_at.desc(), Observation.id),
                      filters.page_number, filters.page_size)
        station_names = dict(self.session.execute(select(Station.id, Station.name)).all())
        file_origins = dict(self.session.execute(
            select(SourceFile.id, SourceFile.origin).where(SourceFile.is_current.is_(True))
        ).all())
        for item in result["items"]:
            item["station_name"] = station_names.get(item["station_id"], "")
            item["source"] = file_origins.get(item["source_file_id"], "")
        return result

    def station_detail(self, filters: StationDetailFilter) -> dict[str, Any] | None:
        station = self.session.get(Station, filters.station_id)
        if station is None:
            return None
        item = serialize(station)
        item["latest_observed_at"] = self.session.scalar(
            select(func.max(Observation.observed_at)).where(Observation.station_id == filters.station_id)
        )
        return item

    def evaluations(self, filters: EvaluationFilter) -> dict[str, Any]:
        statement = select(Evaluation).where(Evaluation.is_current.is_(True))
        if filters.start:
            statement = statement.where(Evaluation.local_date >= filters.start)
        if filters.end:
            statement = statement.where(Evaluation.local_date <= filters.end)
        if filters.station_id:
            statement = statement.where(Evaluation.station_id == filters.station_id)
        if filters.city_id:
            statement = statement.where(Evaluation.station_id.in_(
                select(Station.id).where(Station.city_id == filters.city_id)
            ))
        if filters.pollutant:
            statement = statement.where(Evaluation.pollutant == filters.pollutant)
        if filters.status:
            statement = statement.where(Evaluation.status == filters.status)
        result = page(self.session, statement.order_by(
            Evaluation.local_date.desc(), Evaluation.exceed_ratio.desc(), Evaluation.id
        ), filters.page_number, filters.page_size)
        names = dict(self.session.execute(select(Station.id, Station.name)).all())
        for item in result["items"]:
            item["station_name"] = names.get(item["station_id"], "")
        return result

    def quality(self, filters: QualityFilter, license_confirmed: bool) -> dict[str, Any]:
        statement = (select(Observation).join(SourceFile).join(
            Station, Observation.station_id == Station.id
        ).where(SourceFile.is_current.is_(True), Observation.basis == "hourly"))
        if filters.start:
            statement = statement.where(Observation.local_date >= filters.start)
        if filters.end:
            statement = statement.where(Observation.local_date <= filters.end)
        if filters.city_id:
            statement = statement.where(Station.city_id == filters.city_id)
        rows = self.session.execute(statement.with_only_columns(
            Observation.pollutant, Observation.quality, func.count().label("count")
        ).group_by(Observation.pollutant, Observation.quality)).mappings().all()
        attempts = self.session.scalars(
            select(SourceAttempt).order_by(SourceAttempt.created_at.desc()).limit(30)
        ).all()
        return {"counts": [dict(row) for row in rows], "attempts": [serialize(row) for row in attempts],
                "license_confirmed": license_confirmed}

    def aqi(self, filters: AqiFilter) -> dict[str, Any]:
        return page(self.session, select(AQIResult).where(
            AQIResult.station_id == filters.station_id,
            AQIResult.local_date.between(filters.start, filters.end),
            AQIResult.is_current.is_(True),
        ).order_by(AQIResult.local_date), 1, 1000)

    def forecasts(self, filters: ForecastFilter) -> dict[str, Any]:
        base = select(DerivedValue).where(
            DerivedValue.station_id == filters.station_id,
            DerivedValue.pollutant == filters.pollutant,
            DerivedValue.kind == "forecast",
        )
        batches = self.session.execute(base.with_only_columns(
            DerivedValue.job_id, func.max(DerivedValue.created_at).label("generated_at")
        ).group_by(DerivedValue.job_id).order_by(func.max(DerivedValue.created_at).desc()).limit(20)).mappings().all()
        selected = filters.job_id or (batches[0]["job_id"] if batches else None)
        items = self.session.scalars(
            base.where(DerivedValue.job_id == selected).order_by(DerivedValue.observed_at)
        ).all() if selected else []
        return {"items": [serialize(item) for item in items], "batches": [dict(batch) for batch in batches],
                "job_id": selected, "probability_available": False}

    def imputations(self, filters: ImputationFilter) -> dict[str, Any]:
        begin = datetime.combine(filters.start, datetime.min.time(), LOCAL).astimezone(timezone.utc)
        finish = datetime.combine(filters.end + timedelta(days=1), datetime.min.time(), LOCAL).astimezone(timezone.utc)
        rows = self.session.scalars(select(DerivedValue).where(
            DerivedValue.station_id == filters.station_id,
            DerivedValue.kind == "imputed",
            DerivedValue.pollutant == filters.pollutant,
            DerivedValue.observed_at >= begin,
            DerivedValue.observed_at < finish,
        ).order_by(DerivedValue.observed_at, DerivedValue.created_at.desc()).limit(20000)).all()
        latest: dict[Any, Any] = {}
        for row in rows:
            latest.setdefault(row.observed_at, serialize(row))
        return {"items": list(latest.values()), "scope": "辅助分析，不参与环境质量标准评价"}


    def timeseries(self, filters: TimeseriesFilter) -> dict[str, Any]:
        statement = (select(Observation).join(SourceFile).join(
            Station, Observation.station_id == Station.id
        ).where(SourceFile.is_current.is_(True), Observation.basis == (
            "source_aqi" if filters.pollutant == "AQI" else "hourly"
        )))
        if filters.start:
            statement = statement.where(Observation.local_date >= filters.start)
        if filters.end:
            statement = statement.where(Observation.local_date <= filters.end)
        if filters.city_id:
            statement = statement.where(Station.city_id == filters.city_id)
        if filters.pollutant:
            statement = statement.where(Observation.pollutant == filters.pollutant)
        if filters.station_ids:
            statement = statement.where(Observation.station_id.in_(filters.station_ids))
        group_time = Observation.local_date if filters.resolution == "day" else Observation.observed_at
        aggregate = func.max if filters.pollutant == "AQI" else func.avg
        columns: list[Any] = [group_time.label("time"), aggregate(Observation.value).label("value"),
                   func.count(Observation.value).label("valid_points")]
        groups: list[Any] = [group_time]
        if filters.station_ids:
            columns.append(Observation.station_id)
            groups.append(Observation.station_id)
        grouped = statement.with_only_columns(*columns).group_by(*groups).order_by(group_time)
        rows = self.session.execute(grouped.limit(10001)).mappings().all()
        times = (
            [filters.start + timedelta(days=n) for n in range((filters.end - filters.start).days + 1)]
            if filters.resolution == "day" else [
                datetime.combine(filters.start, datetime.min.time(), LOCAL).astimezone(timezone.utc) + timedelta(hours=n)
                for n in range(((filters.end - filters.start).days + 1) * 24)
            ]
        )
        if len(rows) > 10000 or len(times) * max(1, len(filters.station_ids)) > 10000:
            return {"_too_many": True}
        lookup = {(row["time"], row.get("station_id")): dict(row) for row in rows}
        items = [lookup.get((point, identifier), {
            "time": point, "value": None, "valid_points": 0,
            **({"station_id": identifier} if identifier else {}),
        }) for identifier in (filters.station_ids or (None,)) for point in times]
        label = (
            "AQI（最大值）" if filters.pollutant == "AQI" else
            ("全站平均" if not filters.station_ids else "站点对比")
        )
        return {"items": items, "unit": UNITS.get(filters.pollutant),
                "resolution": filters.resolution, "label": label,
                "pollutant": filters.pollutant}

    def dashboard(self, filters: DashboardFilter) -> dict[str, Any]:
        available = select(
            func.max(Observation.local_date), func.max(SourceFile.created_at)
        ).join(SourceFile).join(
            Station, Station.id == Observation.station_id
        ).where(SourceFile.is_current.is_(True))
        if filters.city_id:
            available = available.where(Station.city_id == filters.city_id)
        city_code = self.session.scalar(select(City.code).where(City.id == filters.city_id)) if filters.city_id else None
        if not filters.city_id or city_code == "beijing":
            latest, updated_at = self.session.execute(select(
                func.max(SourceFile.local_date), func.max(SourceFile.created_at)
            ).where(SourceFile.is_current.is_(True))).one()
        else:
            latest, updated_at = self.session.execute(available).one()
        station_filter: list[Any] = [Station.active.is_(True)]
        if filters.city_id:
            station_filter.append(Station.city_id == filters.city_id)
        selected_end = filters.end or latest
        selected_start = filters.start or (selected_end - timedelta(days=6) if selected_end else None)
        if selected_start and selected_end and (
            selected_end < selected_start or (selected_end - selected_start).days > 731
        ):
            return {"_invalid_range": True}
        statement = (select(Observation).join(SourceFile).join(
            Station, Observation.station_id == Station.id
        ).where(SourceFile.is_current.is_(True), Observation.basis == "hourly"))
        if selected_start:
            statement = statement.where(Observation.local_date >= selected_start)
        if selected_end:
            statement = statement.where(Observation.local_date <= selected_end)
        if filters.city_id:
            statement = statement.where(Station.city_id == filters.city_id)
        summary = self.session.execute(statement.with_only_columns(
            Observation.pollutant, func.avg(Observation.value).label("mean"),
            func.count(Observation.value).label("valid"), func.count().label("total")
        ).group_by(Observation.pollutant)).mappings().all()
        evaluation_filter: list[Any] = [Evaluation.is_current.is_(True)]
        if selected_start:
            evaluation_filter.append(Evaluation.local_date >= selected_start)
        if selected_end:
            evaluation_filter.append(Evaluation.local_date <= selected_end)
        if filters.city_id:
            evaluation_filter.append(Evaluation.station_id.in_(
                select(Station.id).where(Station.city_id == filters.city_id)
            ))
        evaluation_counts = dict(self.session.execute(
            select(Evaluation.status, func.count()).where(*evaluation_filter).group_by(Evaluation.status)
        ).all())
        inspection_statement = select(func.count()).select_from(Inspection).where(Inspection.status != "archived")
        if filters.enforcement_user_id:
            inspection_statement = inspection_statement.where(or_(
                Inspection.assignee_id == filters.enforcement_user_id,
                cast(Inspection.collaborators, JSONB).contains([filters.enforcement_user_id]),
            ))
        pending = self.session.scalar(inspection_statement) if filters.include_pending else None
        latest_aqi = (select(AQIResult.station_id, func.max(AQIResult.local_date).label("d"))
                      .where(AQIResult.is_current.is_(True)).group_by(AQIResult.station_id).subquery())
        snapshot_rows = self.session.execute(
            select(Station.id, Station.name, Station.latitude, Station.longitude,
                   AQIResult.value, AQIResult.local_date, AQIResult.components, AQIResult.complete)
            .select_from(AQIResult)
            .join(latest_aqi, and_(AQIResult.station_id == latest_aqi.c.station_id,
                                   AQIResult.local_date == latest_aqi.c.d))
            .join(Station, Station.id == AQIResult.station_id)
            .where(Station.active.is_(True), AQIResult.is_current.is_(True),
                   *([] if not filters.city_id else [Station.city_id == filters.city_id]))).all()
        station_snapshot: dict[Any, dict[str, Any]] = {}
        for sid, name, lat, lon, value, observed_date, components, complete in snapshot_rows:
            parts = components if isinstance(components, dict) else {}
            primary = max((p for p, c in parts.items() if isinstance(c, dict) and c.get("iaqi") is not None),
                          key=lambda p: parts[p]["iaqi"], default=None)
            station_snapshot.setdefault(sid, {
                "station_id": sid, "name": name, "latitude": lat, "longitude": lon,
                "aqi": value, "local_date": str(observed_date) if observed_date else None,
                "primary": primary, "complete": bool(complete)})
        attribution = self.session.scalar(
            select(SourceFile.attribution).where(SourceFile.is_current.is_(True))
            .order_by(SourceFile.created_at.desc()).limit(1))
        return {
            "latest_date": latest, "updated_at": updated_at,
            "start": selected_start, "end": selected_end,
            "stations": self.session.scalar(select(func.count()).select_from(Station).where(*station_filter)),
            "pollutants": [dict(row) for row in summary], "evaluations": evaluation_counts,
            "pending_inspections": pending,
            "station_snapshot": list(station_snapshot.values()),
            "attribution": attribution or "北京市生态环境监测中心（来源待接入）",
            "source_url": "https://quotsoft.net/air/", "frequency": "每日更新",
            "stale": latest is None or (datetime.now(LOCAL).date() - latest).days > 2,
        }
