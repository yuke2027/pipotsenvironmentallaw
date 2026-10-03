"""Station-level daily assessments from original hourly observations only.

Reference: GB 3095 tables 1/4; HJ 633-2026 table 3; HJ 663 section 6.
No city regulatory assessment is inferred from an unclassified station set.
"""
from collections import defaultdict
from typing import Any
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
import math

from sqlalchemy import and_, or_, select, text, update

from app.v2.domains.collection.repository import LOCAL
from app.v2.common import POLLUTANTS, UNITS, serialize
from app.v2.domains.collection.models import SourceFile
from app.v2.domains.monitoring.models import AQIResult, City, Evaluation, Observation, Standard, Station

IAQI = [0, 50, 100, 150, 200, 300, 400, 500]
BREAKPOINTS = {
    "SO2": [0, 50, 150, 475, 800, 1600, 2100, 2620],
    "NO2": [0, 40, 80, 180, 280, 565, 750, 940],
    "CO": [0, 2, 4, 14, 24, 36, 48, 60],
    "O3": [0, 100, 160, 215, 265, 800],
    "PM10": [0, 50, 150, 250, 350, 420, 500, 600],
    "PM2.5": [0, 35, 75, 115, 150, 250, 350, 500],
}


def rounded(value: float | int, pollutant: str) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1") if pollutant == "CO" else Decimal("1"), rounding=ROUND_HALF_EVEN))


def subindex(pollutant: str, value: float, day: date) -> int | None:
    limits = list(BREAKPOINTS[pollutant])
    if day >= date(2026, 3, 1):
        if pollutant == "PM2.5": limits[2] = 60
        if pollutant == "PM10": limits[2] = 120
    if pollutant == "O3" and value > 800 and day < date(2026, 3, 1):
        return None  # Historical high O3 requires a separate 1h evaluation, never extrapolate 8h.
    if value >= limits[-1]: return IAQI[len(limits) - 1]
    for index in range(1, len(limits)):
        if value <= limits[index]:
            result = (IAQI[index] - IAQI[index-1]) / (limits[index] - limits[index-1]) * (value - limits[index-1]) + IAQI[index-1]
            return math.ceil(result - 1e-10)
    return None


def daily_statistic(pollutant: str, hours: dict[int, float | None]) -> tuple[float | None, int]:
    valid = {h: v for h, v in hours.items() if v is not None and math.isfinite(v) and v >= 0}
    if pollutant == "O3":
        # Preserve source timestamps: windows end at 08:00..24:00 Beijing time.
        # The following day's 00:00 is supplied as hour 24 when available.
        windows = []
        for ending in range(8, 25):
            values = [valid[h] for h in range(ending - 7, ending + 1) if h in valid]
            if len(values) >= 6: windows.append(sum(values) / len(values))
        return (max(windows) if windows else None), len(windows)
    values = list(valid.values())
    return (sum(values) / len(values) if values else None), len(values)


def evaluate_range(db: Any, start: date, end: date, job_id: str, progress: Any, station_id: str | None = None) -> dict[str, Any]:
    total, insufficient, skipped = 0, 0, 0
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        with db.transaction() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"evaluation:{day}"})
            from datetime import datetime, timezone
            midnight = datetime.combine(day + timedelta(days=1), datetime.min.time(), LOCAL).astimezone(timezone.utc)
            statement = select(Observation, SourceFile.sha256).join(SourceFile).where(SourceFile.is_current.is_(True),
                or_(Observation.local_date == day, and_(Observation.pollutant == "O3", Observation.observed_at == midnight)),
                Observation.basis == "hourly")
            if station_id: statement = statement.where(Observation.station_id == station_id)
            observations = session.execute(statement).all()
            grouped: dict[Any, dict[str, dict[int, float | None]]] = defaultdict(lambda: defaultdict(dict))
            hashes: dict[Any, set[Any]] = defaultdict(set)
            for obs, source_hash in observations:
                hashes[obs.station_id].add(source_hash)
                hour = 24 if obs.local_date > day else obs.observed_at.astimezone(LOCAL).hour
                grouped[obs.station_id][obs.pollutant][hour] = obs.value if obs.quality == "valid" and obs.unit == UNITS[obs.pollutant] else None
            standards = session.scalars(select(Standard).where(Standard.enabled.is_(True), Standard.grade == "二级",
                Standard.effective_from <= day, (Standard.effective_to.is_(None) | (Standard.effective_to >= day)))).all()
            station_regions = dict(session.execute(select(Station.id, City.name).join(City)).all())
            for station, pollutants in grouped.items():
                applicable = sorted([s for s in standards if s.region in {"全国", station_regions.get(station)}],
                    key=lambda s: (s.region != "全国", s.effective_from))
                by_pollutant = {s.pollutant: s for s in applicable if s.basis in {"daily_mean", "daily_max_8h"}}
                hash_input = {"sources": sorted(hashes[station]), "standards": [serialize(s) for s in by_pollutant.values()], "method": "daily-v2.2"}
                snapshot = hashlib.sha256(json.dumps(hash_input, sort_keys=True).encode()).hexdigest()
                components = {}
                for pollutant in POLLUTANTS:
                    standard = by_pollutant.get(pollutant)
                    if standard is None: continue
                    raw, count = daily_statistic(pollutant, pollutants.get(pollutant, {}))
                    if raw is None:
                        valid = False
                    else:
                        valid = count >= standard.min_points or (
                            pollutant == "O3" and rounded(raw, pollutant) > standard.limit_value)
                    value = rounded(raw, pollutant) if valid and raw is not None else None
                    status = "insufficient" if not valid else ("exceeded" if value > standard.limit_value else "within")
                    components[pollutant] = {"value": value, "valid_points": count, "status": status,
                                              "iaqi": subindex(pollutant, value, day) if value is not None else None}
                    prior = session.scalar(select(Evaluation).where(Evaluation.station_id == station, Evaluation.local_date == day,
                        Evaluation.pollutant == pollutant, Evaluation.standard_id == standard.id, Evaluation.snapshot_hash == snapshot))
                    if prior:
                        session.execute(update(Evaluation).where(Evaluation.station_id == station, Evaluation.local_date == day,
                            Evaluation.pollutant == pollutant).values(is_current=False))
                        prior.is_current = True
                        skipped += 1
                        continue
                    session.execute(update(Evaluation).where(Evaluation.station_id == station, Evaluation.local_date == day,
                        Evaluation.pollutant == pollutant).values(is_current=False))
                    snapshot_standard = serialize(standard)
                    snapshot_standard.update({"statistical_value": raw, "rounding": "GB/T 8170 half-even; CO 0.1, others 1",
                        "data_scope": "原始小时观测；站点评价；公开源小时采样时长未单独核验", "method": "daily-v2.2",
                        "ozone_window": "按来源时间戳，结束时刻08:00至次日00:00；缺值按每8小时至少6个有效值检查"})
                    session.add(Evaluation(station_id=station, local_date=day, pollutant=pollutant, basis=standard.basis,
                        standard_id=standard.id, standard_snapshot=snapshot_standard, snapshot_hash=snapshot, valid_points=count,
                        value=value, exceed_ratio=max(0, round(value / standard.limit_value - 1, 2)) if valid else None,
                        status=status, job_id=job_id))
                    total += 1
                    insufficient += int(not valid)
                version = "HJ 633—2026" if day >= date(2026, 3, 1) else "HJ 633—2012"
                prior_aqi = session.scalar(select(AQIResult).where(AQIResult.station_id == station, AQIResult.local_date == day,
                    AQIResult.snapshot_hash == snapshot, AQIResult.version == version))
                if prior_aqi is None:
                    session.execute(update(AQIResult).where(AQIResult.station_id == station, AQIResult.local_date == day).values(is_current=False))
                    indices = [c["iaqi"] for c in components.values() if c["iaqi"] is not None]
                    session.add(AQIResult(station_id=station, local_date=day, value=max(indices) if indices else None,
                        components=components, complete=len(indices) == 6, version=version, snapshot_hash=snapshot))
                else:
                    session.execute(update(AQIResult).where(AQIResult.station_id == station, AQIResult.local_date == day).values(is_current=False))
                    prior_aqi.is_current = True
        progress(round(95 * (offset + 1) / ((end-start).days+1)))
    return {"evaluations": total, "insufficient": insufficient, "skipped": skipped,
            "scope": "站点日评价；不推断企业违法，不替代正式监测审核"}
