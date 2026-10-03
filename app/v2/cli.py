"""Explicit administration; creating an admin is never a server-start side effect."""
import argparse
from typing import Any
import getpass
import json
from datetime import date, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.v2.auth import hasher
from app.v2.config import Settings
from app.v2.db import Database
from app.v2.domains.auth.models import User
from app.v2.seed import seed


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    admin = commands.add_parser("create-admin")
    admin.add_argument("--username", required=True)
    admin.add_argument("--display-name", default="平台管理员")
    admin.add_argument("--password-stdin", action="store_true", help="Read and confirm the initial password from stdin")
    commands.add_parser("openapi").add_argument("--output", default="frontend/openapi.json")
    collect = commands.add_parser("collect")
    collect.add_argument("--start", type=date.fromisoformat)
    collect.add_argument("--end", type=date.fromisoformat)
    collect.add_argument("--backfill-months", type=int, choices=[24])
    imported = commands.add_parser("import-folder")
    imported.add_argument("directory", type=Path)
    commands.add_parser("backup-files").add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings()
    if args.command == "openapi":
        from app.v2.main import create_app
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(create_app(settings).openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
        return
    db = Database(settings)
    if args.command == "backup-files":
        from app.v2.backup import archive_files
        from app.v2.storage import FileStore
        settings.prepare()
        print(json.dumps(archive_files(
            db,
            FileStore(settings.storage_root),
            args.output,
            confirmation_path=settings.source_license_confirmation_file,
        )))
        return
    if args.command == "collect":
        from app.v2.jobs import enqueue
        from app.v2.collection import LOCAL
        from datetime import datetime
        from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]
        end = args.end or datetime.now(LOCAL).date() - timedelta(days=1)
        start = args.start or (end + timedelta(days=1) - relativedelta(months=24) if args.backfill_months else end - timedelta(days=6))
        if start > end or (end-start).days > 731: raise SystemExit("Invalid collection range")
        if settings.environment == "production" and not settings.source_license_ready(): raise SystemExit("Source business-use license has not been confirmed")
        with db.transaction() as session:
            job = enqueue(session, "collect", {"start": str(start), "end": str(end)})
            print(json.dumps({"job_id": job.id, "start": str(start), "end": str(end)}))
        return
    if args.command == "import-folder":
        from app.v2.jobs import enqueue
        from app.v2.storage import FileStore
        settings.prepare()
        store = FileStore(settings.storage_root)
        files = sorted(args.directory.resolve().glob("beijing_*.csv"))
        if not files: raise SystemExit("No supported daily CSV files found")
        identifiers = []
        for filename in files:
            kind = "extra" if filename.name.startswith("beijing_extra_") else "all"
            key, hashed = store.put(filename.read_bytes(), "uploads", ".csv")
            with db.transaction() as session:
                job = enqueue(session, "import", {"kind": kind, "storage_key": key, "sha256": hashed})
                identifiers.append(job.id)
        print(json.dumps({"jobs": identifiers, "count": len(identifiers)}))
        return
    if args.command == "migrate":
        config = Config("alembic-v2.ini")
        command.upgrade(config, "head")
        with db.transaction() as session: seed(session)
        print("V2 migration and reference seed completed")
    elif args.command == "create-admin":
        if args.password_stdin:
            password = input().rstrip("\r\n")
            confirmation = input().rstrip("\r\n")
        else:
            password = getpass.getpass("Initial password (12+ characters): ")
            confirmation = getpass.getpass("Confirm password: ")
        if len(password) < 12 or password != confirmation:
            raise SystemExit("Password too short or confirmation mismatch")
        with db.transaction() as session:
            if session.scalar(select(User.id).where(User.role == "管理员")):
                raise SystemExit("An administrator already exists; use account management")
            session.add(User(username=args.username, display_name=args.display_name,
                             role="管理员", password_hash=hasher.hash(password), must_change_password=True))
        print("Administrator created; password change is required at first login")


if __name__ == "__main__":
    main()
