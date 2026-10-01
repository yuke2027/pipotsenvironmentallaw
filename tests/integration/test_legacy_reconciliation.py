"""Legacy reconciliation refuses deletion until the report succeeds."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.reconcile_legacy import main


def _tree(root: Path) -> None:
    legacy = root / "legacy_algorithms"
    legacy.mkdir()
    for name in (
        "data_preprocessing.py",
        "data_imputation.py",
        "train_all_models.py",
        "legal_supervision.py",
    ):
        (legacy / name).write_text("def ok():\n    return 1\n", encoding="utf-8")
    data = root / "data1"
    data.mkdir()
    (data / "beijing_all_20250101.csv").write_text("date,hour,type,东城\n", encoding="utf-8")
    for name in ("数据预处理.ipynb", "数据插补.ipynb", "法律监督体系.ipynb", "jixianfenlei.ipynb"):
        (root / name).write_text("{}\n", encoding="utf-8")
    (root / "view_legal_results.py").write_text("print('old')\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)


@pytest.mark.integration
def test_reconciliation_refuses_deletion_until_the_report_succeeds(tmp_path: Path) -> None:
    _tree(tmp_path)
    report = tmp_path / "report.json"
    assert main(["--root", str(tmp_path), "--report", str(report)]) == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert (tmp_path / "数据预处理.ipynb").is_file()
    (tmp_path / "legacy_algorithms" / "data_preprocessing.py").unlink()
    assert main(["--root", str(tmp_path), "--report", str(report), "--apply-deletion"]) == 1
    assert (tmp_path / "jixianfenlei.ipynb").is_file()
    (tmp_path / "legacy_algorithms" / "data_preprocessing.py").write_text(
        "def ok():\n    return 1\n", encoding="utf-8"
    )
    assert main(["--root", str(tmp_path), "--report", str(report), "--apply-deletion"]) == 0
    assert not (tmp_path / "数据预处理.ipynb").exists()
    assert not (tmp_path / "view_legal_results.py").exists()
    assert (tmp_path / "legacy_algorithms" / "legal_supervision.py").is_file()
    assert (tmp_path / "data1" / "beijing_all_20250101.csv").is_file()
