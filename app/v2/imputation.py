"""Offline imputation with observed-only masks and training-only normalization."""
import tempfile
from pathlib import Path

from typing import Any

import numpy as np
import pandas as pd

from app.v2.common import POLLUTANTS
from app.v2.datasets import scores, splits, train_scaler


def windows(data: Any, stations: Any, bounds: tuple[int, int], window: int) -> Any:
    low, high = bounds
    result = [data[s, start:start+window] for s in stations for start in range(low, high-window+1, window)]
    if not result: raise ValueError("数据不足以生成隔离窗口")
    values = np.array(result)
    return values[np.isfinite(values).mean(axis=(1, 2)) >= .5]


def fixed_mask(data: Any, seed: int, rate: float = .1, block: int = 0) -> Any:
    rng = np.random.default_rng(seed)
    observed = np.isfinite(data)
    if not block:
        mask = rng.random(data.shape) < rate
    else:
        mask = np.zeros(data.shape, dtype=bool)
        for sample in range(len(data)):
            for feature in range(data.shape[2]):
                start = int(rng.integers(0, max(1, data.shape[1] - block + 1)))
                mask[sample, start:start+block, feature] = True
    return mask & observed


def interpolate(data: Any, means: Any) -> Any:
    result = np.empty_like(data)
    for index, sample in enumerate(data):
        frame = pd.DataFrame(sample).interpolate(limit_direction="both")
        result[index] = frame.fillna(dict(enumerate(means))).to_numpy()
    return result


def construct(algorithm: str, window: int, features: int, configuration: Any) -> Any:
    try:
        from pypots.imputation import SAITS, BRITS  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ValueError("PyPOTS 尚未安装，请启用专用模型 Worker 镜像") from exc
    common = dict(n_steps=window, n_features=features, batch_size=16, epochs=configuration.model_epochs,
                  patience=min(5, configuration.model_epochs), device=configuration.model_device, num_workers=0, verbose=False)
    if algorithm == "SAITS": return SAITS(n_layers=2, d_model=64, n_heads=4, d_k=16, d_v=16, d_ffn=128, **common)
    return BRITS(rnn_hidden_size=64, **common)


def train(data: Any, times: Any, stations: Any, algorithm: str, seed: int, window: int, settings: Any, store: Any, progress: Any) -> Any:
    bounds = splits(len(times), window)
    holdout = [len(stations)-1] if len(stations) > 1 else []
    train_stations = list(range(len(stations) - len(holdout)))
    mean, scale = train_scaler(data, bounds[0][1], train_stations)
    train_x, val_x, test_x = [windows(data, train_stations, bound, window) for bound in bounds]
    if any(len(x) == 0 for x in [train_x, val_x, test_x]): raise ValueError("有效观测不足，无法训练和评估")
    model, checkpoint = None, None
    # Seasonal statistics use only training time and training stations.
    hour_means = np.array([np.nanmean(data[train_stations, :bounds[0][1]][:, np.arange(bounds[0][1]) % 24 == h], axis=(0, 1)) for h in range(24)])
    hour_means = np.where(np.isfinite(hour_means), hour_means, mean)
    def seasonal_fill(masked: Any) -> Any:
        # Each evaluated window's phase follows its time-split origin, with the same station-major ordering.
        starts = list(range(bounds[2][0], bounds[2][1]-window+1, window))
        phases = np.array([(start + np.arange(window)) % 24 for _ in train_stations for start in starts])
        all_test = np.array([data[s, start:start+window] for s in train_stations for start in starts])
        phases = phases[np.isfinite(all_test).mean(axis=(1, 2)) >= .5]
        return np.where(np.isfinite(masked), masked, hour_means[phases])
    if algorithm in {"SAITS", "BRITS"}:
        import random
        import torch
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
        torch.use_deterministic_algorithms(True, warn_only=True)
        model = construct(algorithm, window, len(POLLUTANTS), settings)
        validation_mask = fixed_mask(val_x, seed)
        val_corrupted = val_x.copy()
        val_corrupted[validation_mask] = np.nan
        model.fit({"X": (train_x-mean)/scale}, {"X": (val_corrupted-mean)/scale, "X_ori": (val_x-mean)/scale})
        with tempfile.TemporaryDirectory(dir=settings.storage_root / "models") as directory:
            filename = str(Path(directory) / "candidate.pypots")
            model.save(filename)
            key, hashed = store.put(Path(filename).read_bytes(), "models", ".pypots")
            checkpoint = {"storage_key": key, "sha256": hashed}
        reloaded = construct(algorithm, window, len(POLLUTANTS), settings)
        reloaded.load(str(store.verify(key, hashed)))
        probe = (val_corrupted[:2]-mean)/scale
        reload_checked = bool(np.allclose(model.predict({"X": probe})["imputation"], reloaded.predict({"X": probe})["imputation"], atol=1e-5))
        model = reloaded
    else:
        reload_checked = True
    def predict(masked: Any) -> Any:
        if model is None: return interpolate(masked, mean)
        return model.predict({"X": (masked-mean)/scale})["imputation"] * scale + mean
    metrics, passed = {}, True
    scenarios = [("random_10", .1, 0), ("random_30", .3, 0), ("random_50", .5, 0),
                 ("block_6", 0, 6), ("block_24", 0, 24), ("block_72", 0, min(72, window))]
    for index, (name, rate, block) in enumerate(scenarios):
        mask = fixed_mask(test_x, seed+index, rate, block)
        masked = test_x.copy()
        masked[mask] = np.nan
        predictions, baseline = predict(masked), interpolate(masked, mean)
        seasonal = seasonal_fill(masked)
        by_pollutant = {}
        for feature, pollutant in enumerate(POLLUTANTS):
            active = mask[:, :, feature]
            if not active.any(): continue
            score = scores(test_x[:, :, feature][active], predictions[:, :, feature][active])
            reference = scores(test_x[:, :, feature][active], baseline[:, :, feature][active])
            seasonal_score = scores(test_x[:, :, feature][active], seasonal[:, :, feature][active])
            by_pollutant[pollutant] = {"candidate": score, "interpolation": reference, "seasonal_statistic": seasonal_score}
            passed &= score["MAE"] <= reference["MAE"] + 1e-6
            if algorithm in {"SAITS", "BRITS"}: passed &= score["MAE"] <= seasonal_score["MAE"] + 1e-6
        metrics[name] = by_pollutant
        progress(40 + index * 7)
    holdout_scores = None
    if holdout:
        holdout_x = windows(data, holdout, bounds[2], window)
        if len(holdout_x):
            mask = fixed_mask(holdout_x, seed)
            corrupted = holdout_x.copy()
            corrupted[mask] = np.nan
            held_predictions = predict(corrupted)
            holdout_scores = {p: scores(holdout_x[:, :, i][mask[:, :, i]], held_predictions[:, :, i][mask[:, :, i]])
                for i, p in enumerate(POLLUTANTS) if mask[:, :, i].any()}
    artifact = {"algorithm": algorithm, "mean": mean.tolist(), "scale": scale.tolist(), "window": window, "checkpoint": checkpoint}
    return artifact, metrics, {"bounds": bounds, "train_stations": [stations[i] for i in train_stations],
        "holdout_stations": [stations[i] for i in holdout], "station_holdout": holdout_scores,
        "normalizer_fit_end": str(times[bounds[0][1]-1]), "normalizer_fit_scope": "training stations and training time only",
        "no_cross_split_windows": True, "observed_only_masks": True, "mask_seed": seed,
        "reload_checked": reload_checked, "baseline_passed": bool(passed), "mode": "offline (future context within window allowed)"}, bool(passed and reload_checked)


def infer(artifact: dict[str, Any], data: Any, settings: Any, store: Any) -> Any:
    means, scale = np.array(artifact["mean"]), np.array(artifact["scale"])
    if artifact["algorithm"] == "interpolation": return interpolate(data, means)
    model = construct(artifact["algorithm"], artifact["window"], len(POLLUTANTS), settings)
    checkpoint = artifact["checkpoint"]
    model.load(str(store.verify(checkpoint["storage_key"], checkpoint["sha256"])))
    return model.predict({"X": (data-means)/scale})["imputation"] * scale + means
