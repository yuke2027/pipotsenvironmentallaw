"""Consistent DB dump followed by immutable-file backup; restore into a new database only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker","compose","-f",str(ROOT / "compose.platform.yml")]

def run(*args, capture=False):
    return subprocess.run(list(args),cwd=ROOT,check=True,text=True,capture_output=capture)

def container(service): return run(*COMPOSE,"ps","-q",service,capture=True).stdout.strip()

def backup(directory):
    directory.mkdir(parents=True,exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    database_container, api_container = container("postgres"), container("api")
    dump = f"/tmp/platform-{stamp}.dump"
    run("docker","exec",database_container,"pg_dump","-U","platform","-d","platform","--schema=public","-Fc","-f",dump)
    run("docker","cp",f"{database_container}:{dump}",str(directory / "database.dump"))
    archive = f"/workspace/var/platform/backups/{stamp}.tar.gz"
    run("docker","exec",api_container,"python","-m","app.v2.cli","backup-files","--output",archive)
    run("docker","cp",f"{api_container}:{archive}",str(directory / "files.tar.gz"))
    run("docker","cp",f"{api_container}:{archive.removesuffix('.gz')}.manifest.json",str(directory / "files.manifest.json"))
    manifest = {"created_at":stamp,"database_sha256":hashlib.sha256((directory/"database.dump").read_bytes()).hexdigest(),
                "files_sha256":hashlib.sha256((directory/"files.tar.gz").read_bytes()).hexdigest()}
    (directory/"backup.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps({"backup_directory":str(directory),**manifest}))

def verify_restore(directory):
    manifest = json.loads((directory/"backup.json").read_text("utf-8"))
    for filename, key in [("database.dump","database_sha256"),("files.tar.gz","files_sha256")]:
        if hashlib.sha256((directory/filename).read_bytes()).hexdigest() != manifest[key]: raise SystemExit("Backup checksum mismatch")
    files = json.loads((directory/"files.manifest.json").read_text("utf-8"))["files"]
    original_files = dict(files)
    extracted = directory / ("restored-files-" + uuid4().hex[:12])
    extracted.mkdir()
    with tarfile.open(directory/"files.tar.gz","r:gz") as archive:
        for member in archive:
            target = (extracted / member.name).resolve()
            if not member.isfile() or not target.is_relative_to(extracted.resolve()) or member.name not in files: raise SystemExit("Unsafe archive member")
            content = archive.extractfile(member).read()
            if hashlib.sha256(content).hexdigest() != files.pop(member.name): raise SystemExit("File checksum mismatch")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    if files: raise SystemExit("Archive is missing referenced files")
    identifier = "platform_restore_" + uuid4().hex[:12]
    database_container = container("postgres")
    remote = f"/tmp/{identifier}.dump"
    run("docker","cp",str(directory/"database.dump"),f"{database_container}:{remote}")
    run("docker","exec",database_container,"createdb","-U","platform",identifier)
    # This is a newly created empty restore database, never the running database.
    run("docker","exec",database_container,"psql","-U","platform","-d",identifier,"-c","DROP SCHEMA public")
    run("docker","exec",database_container,"pg_restore","-U","platform","-d",identifier,"--no-owner","--no-privileges","--exit-on-error",remote)
    result = run("docker","exec",database_container,"psql","-U","platform","-d",identifier,"-Atc","SELECT count(*) FROM v2_observations; SELECT count(*) FROM v2_attachments;",capture=True)
    referenced = run("docker","exec",database_container,"psql","-U","platform","-d",identifier,"-AtF", "\t", "-c",
        "SELECT storage_key,sha256 FROM v2_source_files "
        "UNION SELECT storage_key,sha256 FROM v2_attachments "
        "UNION SELECT storage_key,sha256 FROM v2_models "
        "UNION SELECT result->>'artifact_key',result->>'artifact_sha256' FROM v2_jobs "
        "WHERE result->>'artifact_key' IS NOT NULL "
        "UNION SELECT artifact->>'key',artifact->>'sha256' FROM v2_jobs "
        "CROSS JOIN LATERAL jsonb_array_elements(COALESCE((result::jsonb -> '_contract' -> 'artifacts'),'[]'::jsonb)) artifact "
        "WHERE artifact->>'key' IS NOT NULL;",capture=True)
    for record in referenced.stdout.splitlines():
        key, hashed = record.split("\t")
        if original_files.get(key) != hashed or hashlib.sha256((extracted/key).read_bytes()).hexdigest() != hashed:
            raise SystemExit("Restored database references a missing/corrupt file")
    report = {"restored_database":identifier,"counts_observations_attachments":result.stdout.splitlines(),
        "restored_files_directory":str(extracted),"restored_file_count":len(original_files),"file_checksums":"all verified against restored database"}
    (directory/"restore-verification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report))

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["backup","verify-restore"])
    parser.add_argument("directory",type=Path)
    args=parser.parse_args()
    destination=args.directory.resolve()
    if args.action == "backup": backup(destination)
    else: verify_restore(destination)
