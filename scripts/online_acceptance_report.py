"""Read-only seven-day operations evidence, never a substitute for elapsed runtime."""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path

from sqlalchemy import func, select
from app.v2.collection import LOCAL
from app.v2.config import Settings
from app.v2.db import Database
from app.v2.domains.admin.models import Delivery
from app.v2.domains.collection.models import SourceAttempt, SourceFile
from app.v2.domains.jobs.models import Job
from app.v2.shared.persistence import now
from app.v2.shared.license import read_license_confirmation


def latest_backup_evidence(root: Path = Path(".artifacts")) -> dict:
    """Return a minimal, non-sensitive summary of the newest restore verification."""
    candidates = sorted(root.rglob("restore-verification.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        return {"available": False}
    path = candidates[0]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False, "path": str(path)}
    return {
        "available": True,
        "path": str(path),
        "restored_file_count": payload.get("restored_file_count", 0),
        "checksums_verified": "verified" in str(payload.get("file_checksums", "")).lower(),
    }


def apply_acceptance_gates(report: dict, source_license_confirmed: bool) -> dict:
    """Compute sign-off gates from recorded evidence without mutating source data."""
    report["collection_coverage_passed"] = bool(report.get("seven_full_days_elapsed")) and all(
        any(job.get("status") in {"succeeded", "partial"} for job in day.get("collection_jobs", []))
        and (day.get("source_attempt_counts", {}).get("success", 0) > 0)
        for day in report.get("days", [])
    )
    license_evidence = report.get("license_evidence")
    evidence_valid = (
        bool(license_evidence.get("valid"))
        if isinstance(license_evidence, dict)
        else True
    )
    report["license_gate_passed"] = bool(source_license_confirmed) and evidence_valid
    backup = report.get("backup_evidence") or {}
    report["backup_gate_passed"] = bool(
        backup.get("available") and backup.get("checksums_verified")
    )
    report["production_signoff_passed"] = (
        report["collection_coverage_passed"]
        and report["license_gate_passed"]
        and report["backup_gate_passed"]
    )
    report["review_required"] = (
        "Review missing files, retries, source revisions, notifications and backup evidence; "
        "coverage alone does not approve production."
    )
    return report


def earliest_review_at(since: datetime) -> str:
    """Return the first instant at which the seven-day window can be reviewed."""
    return (since + timedelta(days=7)).isoformat()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--since', required=True, type=datetime.fromisoformat, help='ISO timestamp with offset')
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    if not args.since.tzinfo: raise SystemExit('--since must include a timezone offset')
    settings=Settings()
    database=Database(settings)
    current=now()
    license_evidence = read_license_confirmation(settings.source_license_confirmation_file)
    report={'since':args.since.isoformat(),'generated_at':current.isoformat(),
        'environment':settings.environment,'source_license_confirmed':settings.source_license_confirmed,
        'license_evidence': license_evidence,
        'earliest_review_at':earliest_review_at(args.since),
        'seven_full_days_elapsed':current-args.since >= timedelta(days=7),'days':[]}
    with database.sessions() as session:
        for index in range(7):
            begin=args.since+timedelta(days=index)
            end=begin+timedelta(days=1)
            jobs=session.scalars(select(Job).where(Job.kind=='collect',Job.created_at>=begin,Job.created_at<end)).all()
            attempts=session.execute(select(SourceAttempt.status,func.count()).where(SourceAttempt.created_at>=begin,
                SourceAttempt.created_at<end).group_by(SourceAttempt.status)).all()
            file_rows=session.execute(select(SourceFile.origin, SourceFile.is_current, func.count()).where(
                SourceFile.local_date >= begin.date(), SourceFile.local_date < end.date()
            ).group_by(SourceFile.origin, SourceFile.is_current)).all()
            report['days'].append({'start':begin.isoformat(),'end':end.isoformat(),'elapsed':end<=current,
                'collection_jobs':[{'id':j.id,'status':j.status,'attempts':j.attempts,'progress':j.progress,'error':j.error} for j in jobs],
                'source_attempt_counts':dict(attempts),
                'source_file_counts':[{'origin':origin,'is_current':is_current,'count':count} for origin,is_current,count in file_rows]})
        report['latest_observation_date']=str(session.scalar(select(func.max(SourceFile.local_date)).where(SourceFile.is_current.is_(True))))
        report['notification_delivery_counts']=dict(session.execute(select(Delivery.status,func.count())
            .where(Delivery.created_at>=args.since).group_by(Delivery.status)).all())
    report['backup_evidence'] = latest_backup_evidence()
    apply_acceptance_gates(report, settings.source_license_ready())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'seven_full_days_elapsed':report['seven_full_days_elapsed'],'collection_coverage_passed':report['collection_coverage_passed'],'license_gate_passed':report['license_gate_passed'],'backup_gate_passed':report['backup_gate_passed'],'production_signoff_passed':report['production_signoff_passed']}))

if __name__=='__main__': main()
