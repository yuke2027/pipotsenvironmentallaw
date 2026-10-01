"""Archive legacy inputs and refuse deletion until the report succeeds."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

NOTEBOOKS = (
    "数据预处理.ipynb",
    "数据插补.ipynb",
    "法律监督体系.ipynb",
    "jixianfenlei.ipynb",
)
LEGACY_FILES = (
    "legacy_algorithms/data_preprocessing.py",
    "legacy_algorithms/data_imputation.py",
    "legacy_algorithms/train_all_models.py",
    "legacy_algorithms/legal_supervision.py",
)
EXTRA_REMOVALS = ("view_legal_results.py",)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_status(root: Path) -> dict[str, object]:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        return {"ok": False, "detail": str(error)}
    if completed.returncode != 0:
        return {"ok": False, "detail": completed.stderr.strip() or "git status failed"}
    return {"ok": True, "porcelain": completed.stdout}


def build_report(root: Path) -> dict[str, object]:
    data_dir = root / "data1"
    archived = []
    if data_dir.is_dir():
        for path in sorted(data_dir.glob("*.csv")):
            archived.append({"path": str(path.relative_to(root)), "sha256": _sha256(path)})
    legacy_present = {relative: (root / relative).is_file() for relative in LEGACY_FILES}
    notebooks = {name: (root / name).is_file() for name in NOTEBOOKS}
    git_status = _git_status(root)
    success = bool(archived) and all(legacy_present.values()) and git_status["ok"] is True
    return {
        "success": success,
        "archive": archived,
        "legacy_present": legacy_present,
        "notebooks_present": notebooks,
        "git": git_status,
    }


def apply_deletion(root: Path, report: dict[str, object]) -> bool:
    if report.get("success") is not True:
        return False
    for name in NOTEBOOKS + EXTRA_REMOVALS:
        path = root / name
        if path.is_file():
            path.unlink()
    for relative in ("Untitled Folder",):
        folder = root / relative
        if folder.is_dir():
            shutil.rmtree(folder)
    nested = root / "pipotsenvironmentallaw"
    if nested.is_dir() and not any(nested.iterdir()):
        nested.rmdir()
    for cache in root.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache)
    for checkpoint in root.rglob(".ipynb_checkpoints"):
        if checkpoint.is_dir():
            shutil.rmtree(checkpoint)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reconcile_legacy")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply-deletion", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(args.root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.apply_deletion and not apply_deletion(args.root, report):
        return 1
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
