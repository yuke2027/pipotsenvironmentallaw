"""Immutable model artifacts. Scalers are JSON arrays, never pickled objects."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.domain.dataframe_contracts import FEATURE_COLUMNS, AlgorithmContractError

FloatArray = NDArray[np.float64]


class ArtifactError(ValueError):
    """A model artifact failed validation. The message contains no secret."""


@dataclass(frozen=True)
class ScalerDocument:
    feature_order: tuple[str, ...]
    mean: FloatArray
    scale: FloatArray
    n_features: int
    n_steps: int
    dtype: str
    schema_version: int = 1


class ArrayStandardizer:
    """Top-level scaler used online. It stores arrays, not a fitted sklearn object."""

    def __init__(self, mean: FloatArray, scale: FloatArray, feature_order: tuple[str, ...]) -> None:
        if feature_order != FEATURE_COLUMNS:
            raise ArtifactError("feature order is not the platform order")
        if mean.shape != (len(feature_order),) or scale.shape != (len(feature_order),):
            raise ArtifactError("scaler length does not match the feature order")
        if not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.any(scale <= 0):
            raise ArtifactError("scale must be positive and finite")
        self.mean = mean.astype(float)
        self.scale = scale.astype(float)
        self.feature_order = feature_order

    def transform(self, values: FloatArray) -> FloatArray:
        self._check_width(values)
        return np.asarray((values - self.mean) / self.scale, dtype=float)

    def inverse_transform(self, values: FloatArray) -> FloatArray:
        self._check_width(values)
        return np.asarray(values * self.scale + self.mean, dtype=float)

    def _check_width(self, values: FloatArray) -> None:
        if values.shape[-1] != len(self.feature_order):
            raise ArtifactError("value shape does not match the feature order")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def assert_inside(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ArtifactError("artifact path escapes the model root") from error
    return resolved


def write_artifact(root: Path, relative: str, payload: dict[str, object], model_bytes: bytes) -> Path:
    """Write scaler, manifest, and model bytes, then rename the directory into place."""

    if relative.endswith(".pkl") or ".." in Path(relative).parts:
        raise ArtifactError("artifact path is not allowed")
    destination = assert_inside(root, root / relative)
    temporary = destination.with_name(destination.name + ".partial")
    if temporary.exists():
        raise ArtifactError("a partial artifact already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(parents=True)
    try:
        (temporary / "model.bin").write_bytes(model_bytes)
        scaler = payload["scaler"]
        (temporary / "scaler.json").write_text(json.dumps(scaler), encoding="utf-8")
        raw_manifest = payload.get("manifest")
        manifest: dict[str, object] = {}
        if isinstance(raw_manifest, dict):
            manifest = {str(key): value for key, value in raw_manifest.items()}
        manifest["sha256"] = hashlib.sha256(model_bytes).hexdigest()
        (temporary / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            for child in temporary.iterdir():
                child.unlink()
            temporary.rmdir()
        raise
    return destination


def load_artifact(root: Path, relative: str) -> tuple[ScalerDocument, str]:
    """Load a manifest and scaler. Missing files, bad checksums, and pickles are rejected."""

    if relative.endswith(".pkl"):
        raise ArtifactError("pickled artifacts are not trusted")
    directory = assert_inside(root, root / relative)
    manifest_path = directory / "manifest.json"
    scaler_path = directory / "scaler.json"
    model_path = directory / "model.bin"
    if not manifest_path.is_file() or not scaler_path.is_file() or not model_path.is_file():
        raise ArtifactError("manifest or scaler is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scaler = json.loads(scaler_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ArtifactError("artifact json is corrupt") from error
    if not isinstance(manifest, dict) or not isinstance(scaler, dict):
        raise ArtifactError("artifact json is not an object")
    actual = sha256_file(model_path)
    if manifest.get("sha256") != actual:
        raise ArtifactError("artifact checksum does not match")
    raw_order = scaler.get("feature_order")
    if not isinstance(raw_order, list) or any(not isinstance(item, str) for item in raw_order):
        raise ArtifactError("feature order is invalid")
    order = tuple(str(item) for item in raw_order)
    try:
        document = ScalerDocument(
            feature_order=order,
            mean=np.asarray(scaler["mean"], dtype=float),
            scale=np.asarray(scaler["scale"], dtype=float),
            n_features=int(scaler["n_features"]),
            n_steps=int(scaler["n_steps"]),
            dtype=str(scaler.get("dtype", "float32")),
            schema_version=int(scaler.get("schema_version", 0)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ArtifactError("scaler document is incomplete") from error
    ArrayStandardizer(document.mean, document.scale, document.feature_order)
    if document.n_features != len(document.feature_order) or document.n_steps < 1:
        raise ArtifactError("artifact shape is not positive")
    return document, actual


def apply_imputation(
    observed: FloatArray,
    missing_mask: NDArray[np.bool_],
    model_output: FloatArray,
) -> tuple[FloatArray, NDArray[np.bool_]]:
    """Fill only missing positions. Observed values and the original mask stay put."""

    if observed.shape != model_output.shape or observed.shape != missing_mask.shape:
        raise ArtifactError("imputation arrays must share a shape")
    filled = observed.copy()
    filled[missing_mask] = model_output[missing_mask]
    return filled, missing_mask.copy()
