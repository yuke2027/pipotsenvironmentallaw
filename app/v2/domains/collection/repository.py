"""Quotsoft daily files: validated UTF-8 wide tables, immutable revisions, resumable jobs."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import insert, select, text, update

from app.v2.common import POLLUTANTS, UNITS
from app.v2.domains.collection.models import SourceAttempt, SourceFile
from app.v2.domains.monitoring.models import City, Observation, Station, StationAlias

LOCAL = ZoneInfo("Asia/Shanghai")
TYPE_MAP = {**{p: (p, "hourly") for p in POLLUTANTS}, "AQI": ("AQI", "source_aqi"),
            **{f"{p}_24h": (p, "rolling_24h") for p in POLLUTANTS if p != "O3"},
            "O3_24h": ("O3", "rolling_max_24h"), "O3_8h": ("O3", "rolling_8h"),
            "O3_8h_24h": ("O3", "rolling_max_8h_24h")}


def parse_wide(content: bytes) -> tuple[date, list[str], list[dict[str, Any]], int]:
    try:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig")))
        header = next(reader)
    except (UnicodeError, StopIteration) as exc:
        raise ValueError("文件必须是非空 UTF-8 CSV") from exc
    if header[:3] != ["date", "hour", "type"] or len(header) < 4 or len(set(header)) != len(header):
        raise ValueError("表头必须为 date,hour,type,站点…，且不能存在重复站点")
    stations = [name.strip() for name in header[3:]]
    if any(not name for name in stations) or len(set(stations)) != len(stations):
        raise ValueError("站点名称为空或重复")
    rows, invalid, dates, seen = [], 0, set(), set()
    for line in reader:
        if len(line) != len(header):
            raise ValueError("CSV 行宽与表头不一致")
        try:
            local_date = datetime.strptime(line[0], "%Y%m%d").date()
            hour = int(line[1])
            if not 0 <= hour <= 23:
                raise ValueError("小时不在 0–23")
        except ValueError as exc:
            raise ValueError("日期或小时格式错误") from exc
        dates.add(local_date)
        if line[2] not in TYPE_MAP:
            continue
        pollutant, basis = TYPE_MAP[line[2]]
        key = (local_date, hour, line[2])
        if key in seen:
            raise ValueError("文件存在重复的日期、小时和指标行")
        seen.add(key)
        instant = datetime.combine(local_date, datetime.min.time(), LOCAL).replace(hour=hour).astimezone(timezone.utc)
        for station, raw in zip(stations, line[3:]):
            quality, value = "valid", None
            if raw.strip() in {"", "NA", "NaN", "nan", "null", "-"}:
                quality = "missing"
            else:
                try:
                    value = float(raw)
                    if not math.isfinite(value) or value < 0:
                        raise ValueError()
                except ValueError:
                    value, quality = None, "invalid"
                    invalid += 1
            rows.append(dict(station_name=station, observed_at=instant, local_date=local_date,
                             pollutant=pollutant, basis=basis, value=value, quality=quality, unit=UNITS[pollutant]))
    if len(dates) != 1 or not rows:
        raise ValueError("每个日文件必须只包含一天，且至少有一种支持的指标")
    return next(iter(dates)), stations, rows, invalid


def import_file(db: Any, store: Any, content: bytes, kind: str, origin: str = "CSV", url: str | None = None, expected_date: date | None = None) -> dict[str, Any]:
    local_date, names, rows, invalid = parse_wide(content)
    if expected_date is not None and expected_date != local_date:
        raise ValueError("来源文件日期不符合请求日期")
    if kind not in {"all", "extra"}:
        raise ValueError("未知日文件类型")
    allowed = {"PM2.5", "PM10", "AQI"} if kind == "all" else {"SO2", "NO2", "O3", "CO"}
    if any(row["pollutant"] not in allowed for row in rows):
        raise ValueError("颗粒物文件和气态文件中的指标不匹配")
    key, hashed = store.put(content, "raw", ".csv")
    source_key = f"beijing/{local_date.isoformat()}/{kind}"
    with db.transaction() as session:
        if db.engine.dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(hashtext('beijing-station-catalog'))"))
            session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": source_key})
        prior = session.scalar(select(SourceFile).where(SourceFile.source_key == source_key, SourceFile.sha256 == hashed))
        if prior:
            if not prior.is_current:
                session.execute(update(SourceFile).where(SourceFile.source_key == source_key).values(is_current=False))
                prior.is_current = True
            return {"date": str(local_date), "kind": kind, "inserted": 0, "skipped": prior.row_count,
                    "invalid": prior.invalid_count, "source_sha256": prior.sha256}
        city = session.scalar(select(City).where(City.code == "beijing"))
        if city is None:
            city = City(code="beijing", name="北京")
            session.add(city)
            session.flush()
        mapping = {}
        for name in names:
            alias = session.scalar(select(StationAlias).where(StationAlias.external_name == name,
                StationAlias.valid_from <= local_date, (StationAlias.valid_to.is_(None) | (StationAlias.valid_to >= local_date))))
            if alias:
                mapping[name] = alias.station_id
                continue
            station = session.scalar(select(Station).where(Station.city_id == city.id, Station.code == name))
            if station is None:
                station = Station(city_id=city.id, code=name, name=name)
                session.add(station)
                session.flush()
            mapping[name] = station.id
            session.add(StationAlias(station_id=station.id, external_name=name))
        session.execute(update(SourceFile).where(SourceFile.source_key == source_key).values(is_current=False))
        source = SourceFile(source_key=source_key, local_date=local_date, kind=kind, origin=origin, url=url,
                            sha256=hashed, storage_key=key, row_count=len(rows), invalid_count=invalid)
        session.add(source)
        session.flush()
        payload = [{**{k: v for k, v in row.items() if k != "station_name"},
                    "station_id": mapping[row["station_name"]], "source_file_id": source.id} for row in rows]
        session.execute(insert(Observation), payload)
    return {"date": str(local_date), "kind": kind, "inserted": len(rows), "skipped": 0,
            "invalid": invalid, "source_sha256": hashed}


def collect_range(db: Any, store: Any, settings: Any, start: date, end: date, job_id: str, progress: Any, client: Any = None) -> dict[str, Any]:
    if end < start or (end - start).days > 731:
        raise ValueError("采集范围应为最多 732 天的有效区间")
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    owned = client is None
    client = client or httpx.Client(timeout=settings.source_timeout_seconds, follow_redirects=True)
    total = ((end - start).days + 1) * 2
    # Resume this delivery only. A new scheduled job still rechecks late revisions.
    with db.sessions() as session:
        completed = set(session.execute(select(SourceAttempt.local_date, SourceAttempt.kind)
            .where(SourceAttempt.job_id == job_id, SourceAttempt.status == "success")).all())
    last_request = 0.0
    try:
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            for kind in ("all", "extra"):
                if (day, kind) in completed:
                    results.append({"date": str(day), "kind": kind, "inserted": 0, "skipped": 0, "resumed": True})
                    progress(round(90 * (len(results) + len(failures)) / total))
                    continue
                url = f"{settings.source_base_url}/beijing_{kind}_{day:%Y%m%d}.csv"
                error = None
                for attempt in range(4):
                    time.sleep(max(0.0, settings.source_interval_seconds - (time.monotonic() - last_request)))
                    last_request = time.monotonic()
                    try:
                        response = client.get(url)
                        response.raise_for_status()
                        if len(response.content) > settings.max_upload_bytes:
                            raise ValueError("来源文件超过大小限制")
                        result = import_file(db, store, response.content, kind, "ONLINE", url, expected_date=day)
                        results.append(result)
                        error = None
                        break
                    except (httpx.HTTPError, ValueError) as exc:
                        error = f"{type(exc).__name__}: {str(exc)[:300]}"
                        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
                            break
                        if attempt < 3:
                            time.sleep(2 ** attempt)
                with db.transaction() as session:
                    session.add(SourceAttempt(local_date=day, kind=kind, job_id=job_id,
                                              status="failed" if error else "success", message=error))
                if error:
                    failures.append({"date": str(day), "kind": kind, "error": error})
                progress(round(90 * (len(results) + len(failures)) / total))
    finally:
        if owned:
            client.close()
    with db.sessions() as session:
        source_hashes = sorted(set(session.scalars(select(SourceFile.sha256).join(
            SourceAttempt,
            (SourceAttempt.local_date == SourceFile.local_date) &
            (SourceAttempt.kind == SourceFile.kind),
        ).where(SourceAttempt.job_id == job_id, SourceAttempt.status == "success")).all()))
    return {"files": results, "failures": failures, "inserted": sum(r["inserted"] for r in results),
            "skipped": sum(r["skipped"] for r in results), "source_hashes": source_hashes,
            "attribution": "https://quotsoft.net/air/"}
