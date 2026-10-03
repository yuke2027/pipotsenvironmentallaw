"""Model orchestration, immutable manifests and activation-safe inference."""
import io
import json
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import insert, select

from app.v2.common import POLLUTANTS
from app.v2.domains.ml.dataset_repository import build_dataset, environment_manifest
from app.v2.domains.ml.models import DerivedValue, ModelActivation, ModelArtifact


def _derived_artifact(store: Any, job: Any, model_id: str, snapshot: dict[str, Any], data_cutoff: Any, row_count: int, kind: str) -> dict[str, Any]:
    """Persist a small immutable manifest for database-backed derived values."""
    manifest = {
        "artifact_kind": kind,
        "job_id": job.id,
        "model_id": model_id,
        "row_count": row_count,
        "data_cutoff": str(data_cutoff),
        "snapshot_hash": snapshot["sha256"],
        "source_hashes": snapshot.get("source_hashes", []),
    }
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    key, hashed = store.put(encoded, "derived", ".json")
    return {
        "artifact_key": key,
        "artifact_sha256": hashed,
        "artifact_kind": kind,
        "artifact_media_type": "application/json",
    }


def model_job(db: Any, store: Any, settings: Any, job: Any, progress: Any) -> dict[str, Any]:
    parameters = job.parameters
    data, times, stations, snapshot = build_dataset(db, store, parameters)
    progress(10)
    if job.kind == "train":
        seed = parameters.get("seed", 42)
        algorithm, task = parameters["algorithm"], parameters["task"]
        if task == "forecast":
            from app.v2 import forecasting
            artifact, metrics, validation, passed = forecasting.train(data, times, stations, algorithm, seed, settings.model_window, progress)
        else:
            from app.v2 import imputation
            artifact, metrics, validation, passed = imputation.train(data, times, stations, algorithm, seed, settings.model_window, settings, store, progress)
        encoded = json.dumps(artifact, ensure_ascii=False, allow_nan=False).encode()
        key, hashed = store.put(encoded, "models", ".json")
        reload_matches = json.loads(store.verify(key, hashed).read_text("utf-8")) == artifact
        manifest = {"snapshot": snapshot, "environment": environment_manifest(), "seed": seed,
                    "parameters": parameters, "validation": validation, "json_reload_verified": reload_matches,
                    "legacy_difference": "旧 LSTM 无隔离回测及区间校准，保留历史制品；新版以原尺度基线指标评估，不要求复现旧输出"}
        with db.transaction() as session:
            prior = session.scalar(select(ModelArtifact).where(ModelArtifact.job_id == job.id))
            if prior:
                return {"model_id": prior.id, "status": prior.status,
                        "artifact_key": prior.storage_key, "artifact_sha256": prior.sha256,
                        "artifact_kind": "model", "artifact_media_type": "application/json",
                        "snapshot_hash": manifest["snapshot"]["sha256"],
                        "source_hashes": manifest["snapshot"].get("source_hashes", [])}
            model = ModelArtifact(task=task, algorithm=algorithm, status="validated" if passed and reload_matches else "experimental",
                                  storage_key=key, sha256=hashed, manifest=manifest, metrics=metrics, job_id=job.id)
            session.add(model)
            session.flush()
            return {"model_id": model.id, "status": model.status, "metrics": metrics,
                    "snapshot_hash": snapshot["sha256"], "source_hashes": snapshot.get("source_hashes", []),
                    "artifact_key": key, "artifact_sha256": hashed,
                    "artifact_kind": "model", "artifact_media_type": "application/json"}
    task = "forecast" if job.kind == "forecast" else "imputation"
    with db.sessions() as session:
        activation = session.get(ModelActivation, task)
        if activation is None: raise ValueError("没有已激活且通过验证的模型，请先在模型中心训练并发布")
        model = session.get(ModelArtifact, activation.model_id)
        artifact = json.loads(store.verify(model.storage_key, model.sha256).read_text("utf-8"))
        validation = model.manifest["validation"]
    records = []
    if job.kind == "forecast":
        from app.v2.forecasting import predict
        window = validation["window"]
        future = pd.date_range(times[-1] + pd.Timedelta(hours=1), periods=24, freq="h")
        if data.shape[1] < window: raise ValueError("推理输入时间窗口不足")
        for s, station in enumerate(stations):
            for feature, pollutant in enumerate(POLLUTANTS[:2]):
                if parameters.get("pollutant") and parameters["pollutant"] != pollutant: continue
                history = data[s, -window:, feature]
                if np.isfinite(history[-24:]).sum() < 18: continue
                values, radius = predict(artifact, pollutant, history, future)
                for timestamp, value in zip(future, values):
                    records.append(dict(station_id=station, observed_at=timestamp.to_pydatetime(), pollutant=pollutant,
                        kind="forecast", value=float(value), lower=max(0, float(value-radius)), upper=float(value+radius)))
    else:
        from app.v2.imputation import infer
        window = artifact["window"]
        for s, station in enumerate(stations):
            for start in range(0, len(times), window):
                actual = data[s, start:start+window]
                if len(actual) < window: continue  # No synthetic padding; partial tail is reported below.
                if np.isfinite(actual).mean() < .5: continue
                prediction = infer(artifact, actual[None, :, :], settings, store)[0]
                for offset, feature in zip(*np.where(~np.isfinite(actual))):
                    value = float(prediction[offset, feature])
                    if not np.isfinite(value): continue
                    records.append(dict(station_id=station, observed_at=times[start+offset].to_pydatetime(), pollutant=POLLUTANTS[feature],
                                        kind="imputed", value=max(0, value), lower=None, upper=None))
    if not records: raise ValueError("没有满足模型输入完整性要求的结果，或范围内无需插补")
    with db.transaction() as session:
        if not session.scalar(select(DerivedValue.id).where(DerivedValue.job_id == job.id).limit(1)):
            session.execute(insert(DerivedValue), [{**record, "model_id": model.id, "job_id": job.id,
                "data_cutoff": times[-1].to_pydatetime(), "snapshot_hash": snapshot["sha256"]} for record in records])
    kind = "forecast" if job.kind == "forecast" else "imputation"
    result = {"rows": len(records), "model_id": model.id, "snapshot_hash": snapshot["sha256"],
              "source_hashes": snapshot.get("source_hashes", []), "data_cutoff": str(times[-1]),
              "partial_tail_hours": len(times) % artifact.get("window", 1),
              "probability_available": False}
    result.update(_derived_artifact(store, job, model.id, snapshot, times[-1], len(records), kind))
    return result
