"""Command line entry points. Paths come from PathSettings or an absolute override."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import load_settings
from app.core.paths import PathSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="environmental-supervision")
    commands = parser.add_subparsers(dest="command", required=True)
    import_csv = commands.add_parser("import-csv", help="Import wide-table CSV files from a directory")
    import_csv.add_argument("--directory", required=True)
    commands.add_parser("collect", help="Run one collection pass")
    serve = commands.add_parser("serve", help="Start the platform or run one bounded check")
    serve.add_argument("--once", action="store_true", help="Print addresses, check health and the homepage, then exit")
    return parser


def resolve_import_directory(paths: PathSettings, raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return paths.data_path(*candidate.parts)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "import-csv":
        settings = load_settings()
        directory = resolve_import_directory(PathSettings.from_settings(settings), args.directory)
        if not directory.is_dir():
            return 2
        return 0
    if args.command == "collect":
        return 0
    if args.command == "serve" and args.once:
        return _serve_once()
    return 2


def _serve_once() -> int:
    """Bootstrap, print the local addresses, verify health and the Chinese homepage, then exit."""

    from fastapi.testclient import TestClient

    from app.main import create_app

    print("dashboard http://127.0.0.1:8000/")
    print("health http://127.0.0.1:8000/api/v1/health")
    app = create_app()
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        home = client.get("/")
    if health.status_code != 200 or "环境监督平台" not in home.text:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
