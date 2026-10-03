"""Append-only file bundle; verify every referenced file before declaring backup valid."""
import hashlib
import json
from pathlib import Path
from typing import Any
import tarfile

from sqlalchemy import select
from app.v2.domains.collection.models import SourceFile
from app.v2.domains.enforcement.models import Attachment
from app.v2.domains.jobs.models import Job
from app.v2.domains.ml.models import ModelArtifact


def _confirmation_file(store: Any, confirmation_path: Path | None = None) -> Path:
    confirmation = (
        store.root / "source-license-confirmation.json"
        if confirmation_path is None
        else Path(confirmation_path).expanduser()
    )
    return confirmation if confirmation.is_absolute() else confirmation.resolve()


def referenced_payload_files(payload: dict[str, Any] | None) -> dict[str, str]:
    """Collect direct and contract-level file references from a job payload."""
    if not isinstance(payload, dict):
        return {}
    references = {}
    if payload.get("storage_key") and payload.get("sha256"):
        references[payload["storage_key"]] = payload["sha256"]
    if payload.get("artifact_key") and payload.get("artifact_sha256"):
        references[payload["artifact_key"]] = payload["artifact_sha256"]
    contract = payload.get("_contract") or {}
    for artifact in contract.get("artifacts", []):
        if artifact.get("key") and artifact.get("sha256"):
            references[artifact["key"]] = artifact["sha256"]
    return references


def file_manifest(db: Any, store: Any, confirmation_path: Path | None = None) -> dict[str, Any]:
    references = {}
    confirmation = _confirmation_file(store, confirmation_path)
    if confirmation.is_file():
        references[confirmation.name] = hashlib.sha256(confirmation.read_bytes()).hexdigest()
    with db.sessions() as session:
        for model in [SourceFile, Attachment, ModelArtifact]:
            for row in session.scalars(select(model)):
                references[row.storage_key] = row.sha256
                if isinstance(row, ModelArtifact):
                    snapshot = row.manifest.get("snapshot",{})
                    if snapshot.get("storage_key"): references[snapshot["storage_key"]] = snapshot["sha256"]
                    payload = json.loads(store.verify(row.storage_key,row.sha256).read_text("utf-8"))
                    checkpoint = payload.get("checkpoint")
                    if checkpoint: references[checkpoint["storage_key"]] = checkpoint["sha256"]
        for row in session.scalars(select(Job)):
            for payload in [row.parameters,row.result]:
                references.update(referenced_payload_files(payload))
    return references


def archive_files(db: Any, store: Any, destination: Any, confirmation_path: Path | None = None) -> dict[str, Any]:
    references = file_manifest(db, store, confirmation_path=confirmation_path)
    confirmation = _confirmation_file(store, confirmation_path)
    destination = Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(destination,"w:gz") as archive:
        for key, hashed in references.items():
            source = confirmation if key == confirmation.name and confirmation.is_file() else store.verify(key, hashed)
            archive.add(source, arcname=key, recursive=False)
    metadata = {"files":references,"archive_sha256":hashlib.sha256(destination.read_bytes()).hexdigest()}
    destination.with_suffix(".manifest.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"files":len(references),"archive_sha256":metadata["archive_sha256"]}
