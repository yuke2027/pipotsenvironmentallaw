"""Inventory the legacy assets without moving or deleting anything."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
paths = []
for name in ["data", "data1", "results", "result_saving", "legacy_algorithms"]:
    for path in sorted((root / name).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            paths.append({"path":str(path.relative_to(root)).replace("\\","/"),"bytes":path.stat().st_size,
                          "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
for path in root.glob("*.ipynb"):
    paths.append({"path":path.name,"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
output = root / "docs" / "legacy-inventory.json"
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps({"baseline_commit":"a044b23","files":paths},ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"files":len(paths),"bytes":sum(row["bytes"] for row in paths)}))
