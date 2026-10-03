"""Immutable hourly matrices and global time boundaries for reproducible experiments."""
from typing import Any

import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.v2.common import POLLUTANTS
from app.v2.domains.collection.models import SourceFile
from app.v2.domains.monitoring.models import Observation


def build_dataset(db: Any, store: Any, parameters: dict[str, Any]) -> Any:
    from datetime import date
    start, end = date.fromisoformat(parameters["start"]), date.fromisoformat(parameters["end"])
    with db.sessions() as session:
        statement = select(Observation.station_id, Observation.observed_at, Observation.pollutant, Observation.value,
                           SourceFile.sha256).join(SourceFile).where(SourceFile.is_current.is_(True),
                           Observation.local_date.between(start, end), Observation.basis == "hourly", Observation.pollutant.in_(POLLUTANTS))
        if parameters.get("station_id"): statement = statement.where(Observation.station_id == parameters["station_id"])
        rows = session.execute(statement).all()
    if not rows: raise ValueError("所选范围没有原始观测数据")
    frame = pd.DataFrame(rows, columns=["station", "time", "pollutant", "value", "source_hash"])
    times = pd.date_range(pd.Timestamp(start).tz_localize("Asia/Shanghai").tz_convert("UTC"),
                          pd.Timestamp(end).tz_localize("Asia/Shanghai").tz_convert("UTC") + pd.Timedelta(hours=23), freq="h")
    stations = sorted(frame.station.unique())
    matrices = []
    for station in stations:
        subset = frame[frame.station == station].pivot(index="time", columns="pollutant", values="value")
        matrices.append(subset.reindex(index=times, columns=list(POLLUTANTS)).to_numpy(dtype=float))
    data = np.array(matrices, dtype=np.float32)
    buffer = io.BytesIO()
    np.savez_compressed(buffer, values=data, stations=np.array(stations), timestamps=times.asi8, pollutants=np.array(POLLUTANTS))  # type: ignore[attr-defined]
    key, hashed = store.put(buffer.getvalue(), "datasets", ".npz")
    return data, times, stations, {"storage_key": key, "sha256": hashed, "source_hashes": sorted(frame.source_hash.unique()),
                                 "start": str(start), "end": str(end), "shape": list(data.shape),
                                 "availability": "latest preserved source revision; historical publication timestamps unavailable",
                                 "backtest_scope": "observation-time causal split; not a historical publication-time replay"}


def splits(length: int, window: int, horizon: int = 0) -> Any:
    edges = [0, int(length * .7), int(length * .85), length]
    if any(edges[i+1] - edges[i] < window + max(1, horizon) for i in range(3)):
        raise ValueError(f"数据时间跨度不足以隔离训练/验证/测试窗口，请选择至少 {int((window + max(1,horizon))/.15/24)+2} 天")
    return [(edges[i], edges[i+1]) for i in range(3)]


def train_scaler(data: Any, train_end: int, train_stations: Any) -> Any:
    training = data[train_stations, :train_end]
    mean = np.nanmean(training, axis=(0, 1))
    scale = np.nanstd(training, axis=(0, 1))
    if not np.all(np.isfinite(mean)): raise ValueError("训练集缺少一种或多种污染物，不能拟合归一化器")
    return mean, np.where(scale > 1e-6, scale, 1.0)


def scores(truth: Any, predictions: Any) -> dict[str, float]:
    valid = np.isfinite(truth) & np.isfinite(predictions)
    if not valid.any(): raise ValueError("评估位置没有可比较的真实观测")
    error = np.asarray(predictions)[valid] - np.asarray(truth)[valid]
    return {"MAE": float(np.mean(np.abs(error))), "RMSE": float(np.sqrt(np.mean(error**2))), "n": int(valid.sum())}


def environment_manifest() -> dict[str, Any]:
    names = ["numpy", "pandas", "scikit-learn", "lightgbm", "torch", "pypots"]
    packages = {}
    for name in names:
        try: packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: pass
    root = Path(__file__).parent
    code_hash = hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in sorted(root.glob("*.py")))).hexdigest()
    return {"python": platform.python_version(), "packages": packages, "code_sha256": code_hash}
