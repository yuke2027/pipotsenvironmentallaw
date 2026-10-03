"""Run actual models on preserved source CSV files; separate from synthetic unit tests."""
import argparse
from datetime import date
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from app.v2.collection import parse_wide
from app.v2.common import POLLUTANTS
from app.v2.config import Settings
from app.v2.datasets import environment_manifest
from app.v2.storage import FileStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("data1"))
    parser.add_argument("--output", type=Path, default=Path(".artifacts/model-validation"))
    parser.add_argument("--algorithms", nargs="+", default=["seasonal", "lightgbm", "interpolation", "SAITS", "BRITS"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records, source_hashes = [], []
    import hashlib
    for path in sorted(args.directory.glob("beijing_*_202501*.csv")):
        content = path.read_bytes()
        _, names, rows, _ = parse_wide(content)
        source_hashes.append(hashlib.sha256(content).hexdigest())
        selected = names[:3]
        for row in rows:
            if row["basis"] == "hourly" and row["station_name"] in selected:
                records.append((row["station_name"], row["observed_at"], row["pollutant"], row["value"]))
    frame = pd.DataFrame(records, columns=["station", "time", "pollutant", "value"])
    if frame.empty: raise SystemExit("No preserved January 2025 source files")
    times = pd.date_range(frame.time.min(), frame.time.max(), freq="h")
    stations = sorted(frame.station.unique())
    data = np.array([frame[frame.station == station].pivot(index="time", columns="pollutant", values="value")
        .reindex(index=times, columns=list(POLLUTANTS)).to_numpy(dtype=float) for station in stations], dtype=np.float32)
    settings = Settings().model_copy(update={"model_window":24,"model_epochs":2,"model_device":"cpu","storage_root":args.output / "storage"})
    settings.prepare()
    store = FileStore(settings.storage_root)
    import torch
    torch.set_num_threads(2)
    report = {"input": {"source_files":len(source_hashes),"source_sha256":source_hashes,"stations":stations,"shape":list(data.shape),
        "start":str(times[0]),"end":str(times[-1]),"original_observation_fraction":float(np.isfinite(data).mean())}, "environment":environment_manifest(),"results":{}}
    for algorithm in args.algorithms:
        started = time.monotonic()
        if algorithm in {"seasonal", "lightgbm"}:
            from app.v2.forecasting import train, predict
            artifact, metrics, manifest, passed = train(data,times,stations,algorithm,42,24,lambda _:None)
            prediction, radius = predict(artifact,"PM2.5",data[0,-24:,0],pd.date_range(times[-1]+pd.Timedelta(hours=1),periods=24,freq="h"))
            assert len(prediction) == 24 and np.isfinite(prediction).all()
        else:
            from app.v2.imputation import train, infer
            artifact, metrics, manifest, passed = train(data,times,stations,algorithm,42,24,settings,store,lambda _:None)
            prediction = infer(artifact,data[:1,-24:,:],settings,store)
            assert prediction.shape == (1,24,6) and np.isfinite(prediction).all()
        artifact_json = json.dumps(artifact,ensure_ascii=False,allow_nan=False)
        key, hashed = store.put(artifact_json.encode(),"models",".json")
        assert json.loads(store.verify(key,hashed).read_text("utf-8")) == artifact
        report["results"][algorithm] = {"metrics":metrics,"validation":manifest,"publication_gate_passed":passed,
            "inference_finite":True,"elapsed_seconds":round(time.monotonic()-started,2),"artifact_sha256":hashed}
        (args.output / "report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
        print(json.dumps({"algorithm":algorithm,"publication_gate_passed":passed,"seconds":report["results"][algorithm]["elapsed_seconds"]}),flush=True)

if __name__ == "__main__": main()
