"""Direct 24-hour forecasts with chronological rolling backtests."""
from typing import Any

import numpy as np

from app.v2.datasets import scores, splits

FEATURES = ["lag1", "lag2", "lag3", "lag24", "lag48", "lag168", "mean24", "std24", "hour_sin", "hour_cos", "weekday", "horizon"]


def features(history: Any, timestamp: Any, horizon: int, fill: Any) -> Any:
    valid = history[np.isfinite(history)]
    fallback = float(valid[-1]) if len(valid) else fill
    lags = [float(history[-lag]) if len(history) >= lag and np.isfinite(history[-lag]) else fallback for lag in [1, 2, 3, 24, 48, 168]]
    last = history[-24:]
    finite = last[np.isfinite(last)]
    mean, std = (float(finite.mean()), float(finite.std())) if len(finite) else (fill, 0)
    return lags + [mean, std, float(np.sin(timestamp.hour * np.pi / 12)), float(np.cos(timestamp.hour * np.pi / 12)), timestamp.weekday(), horizon]


def baseline(history: Any, horizon: int, fill: Any) -> Any:
    value = history[-24 + (horizon-1) % 24] if len(history) >= 24 else np.nan
    return float(value) if np.isfinite(value) else fill


def samples(data: Any, times: Any, station_indices: Any, bounds: Any, pollutant: int, window: int, fill: Any) -> Any:
    X, y, seasonal = [], [], []
    low, high = bounds
    for station in station_indices:
        values = data[station, :, pollutant]
        for cut in range(low + window, high - 23, 24):
            history = values[cut-window:cut]
            if np.isfinite(history).sum() < window * .5: continue
            for horizon in range(1, 25):
                target = values[cut + horizon - 1]
                if not np.isfinite(target): continue
                X.append(features(history, times[cut+horizon-1], horizon, fill))
                y.append(target)
                seasonal.append(baseline(history, horizon, fill))
    if not y: raise ValueError("划分后缺少可用的完整预测样本")
    return np.array(X), np.array(y), np.array(seasonal)


def train(data: Any, times: Any, stations: Any, algorithm: str, seed: int, window: int, progress: Any) -> Any:
    bounds = splits(len(times), window, 24)
    holdout = [len(stations)-1] if len(stations) > 1 else []
    train_stations = list(range(len(stations)-len(holdout)))
    artifact: dict[str, Any] = {"algorithm": algorithm, "features": FEATURES, "pollutants": {}}
    metrics: dict[str, Any] = {}
    passed, reload_checked = True, True
    for p, name in enumerate(["PM2.5", "PM10"]):
        fill = float(np.nanmedian(data[train_stations, :bounds[0][1], p]))
        if not np.isfinite(fill): raise ValueError(f"训练集缺少 {name}")
        train_x, train_y, _ = samples(data, times, train_stations, bounds[0], p, window, fill)
        val_x, val_y, val_base = samples(data, times, train_stations, bounds[1], p, window, fill)
        test_x, test_y, test_base = samples(data, times, train_stations, bounds[2], p, window, fill)
        model_string = None
        if algorithm == "lightgbm":
            try:
                import lightgbm as lgb
            except ImportError as exc:
                raise ValueError("LightGBM 尚未安装，请启用模型 Worker 镜像") from exc
            model = lgb.LGBMRegressor(n_estimators=200, max_depth=7, num_leaves=31, learning_rate=.04,
                random_state=seed, n_jobs=2, verbosity=-1, deterministic=True, force_col_wise=True)
            model.fit(train_x, train_y)
            val_pred, test_pred = np.maximum(0, model.predict(val_x)), np.maximum(0, model.predict(test_x))
            model_string = model.booster_.model_to_string()
            reloaded = lgb.Booster(model_str=model_string)
            reload_checked &= bool(np.allclose(test_pred, np.maximum(0, reloaded.predict(test_x)), atol=1e-8))
        else:
            val_pred, test_pred = val_base, test_base
        # Validation residuals calibrate a nominal 90% interval; test data only measures coverage.
        residuals = np.abs(val_y - val_pred)
        quantile = min(1, np.ceil((len(residuals) + 1) * .9) / len(residuals))
        radius = float(np.quantile(residuals, quantile, method="higher"))
        score, reference = scores(test_y, test_pred), scores(test_y, test_base)
        score["coverage_90"] = float(np.mean((test_y >= np.maximum(0, test_pred-radius)) & (test_y <= test_pred+radius)))
        score["mean_interval_width"] = float(np.mean(test_pred+radius-np.maximum(0,test_pred-radius)))
        candidate_ok = score["MAE"] <= reference["MAE"] and scores(val_y, val_pred)["MAE"] <= scores(val_y, val_base)["MAE"]
        passed &= candidate_ok
        holdout_score = None
        if holdout:
            hx, hy, hb = samples(data, times, holdout, bounds[2], p, window, fill)
            hp = np.maximum(0, reloaded.predict(hx)) if model_string else hb
            holdout_score = scores(hy, hp)
        metrics[name] = {"test": score, "baseline": reference, "validation": scores(val_y, val_pred),
                         "station_holdout": holdout_score, "baseline_passed": candidate_ok}
        artifact["pollutants"][name] = {"fill": fill, "radius": radius, "model_string": model_string}
        progress(40 + p * 30)
    return artifact, metrics, {"bounds": bounds, "window": window, "horizon": 24,
        "train_stations": [stations[i] for i in train_stations], "holdout_stations": [stations[i] for i in holdout],
        "no_cross_split_windows": True, "feature_cutoff": "strictly before forecast origin",
        "interval": "validation residual calibration; nominal 90%, no probability claim",
        "reload_checked": reload_checked, "baseline_passed": bool(passed)}, bool(passed and reload_checked)


def predict(artifact: dict[str, Any], pollutant: str, history: Any, future_times: Any) -> Any:
    meta = artifact["pollutants"][pollutant]
    if artifact["algorithm"] == "lightgbm":
        import lightgbm as lgb
        model = lgb.Booster(model_str=meta["model_string"])
        values = model.predict(np.array([features(history, t, h, meta["fill"]) for h, t in enumerate(future_times, 1)]))
    else:
        values = np.array([baseline(history, h, meta["fill"]) for h in range(1, 25)])
    return np.maximum(0, values), meta["radius"]
