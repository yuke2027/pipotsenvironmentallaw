"""One independently supervised scheduler; durable outbox and missed-job recovery."""
import logging
from typing import Any
import signal
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.v2.config import Settings
from app.v2.db import Database
from app.v2.enforcement import notify
from app.v2.jobs import MODEL_JOBS, enqueue
from app.v2.domains.enforcement.models import Inspection, Rectification
from app.v2.domains.jobs.models import Job, Outbox
from app.v2.shared.persistence import now

logger = logging.getLogger(__name__)
LOCAL = ZoneInfo("Asia/Shanghai")


def publish_outbox(db: Any, sender: Any) -> None:
    with db.transaction() as session:
        messages = session.scalars(select(Outbox).where(Outbox.sent_at.is_(None)).order_by(Outbox.created_at).limit(50).with_for_update(skip_locked=True)).all()
        for message in messages:
            job = session.get(Job, message.job_id)
            sender(job.id, "models" if job.kind in MODEL_JOBS else "io")
            message.sent_at = now()


def recover_stalled(db: Any) -> None:
    with db.transaction() as session:
        jobs = session.scalars(select(Job).where(Job.status.in_(["queued", "running"])).with_for_update(skip_locked=True)).all()
        for job in jobs:
            message = session.scalar(select(Outbox).where(Outbox.job_id == job.id))
            if not message or not message.sent_at: continue
            reference = job.heartbeat_at or message.sent_at
            # Queued tasks may wait behind model training. Resending is harmless under the job lock.
            if reference < now() - timedelta(minutes=10):
                message.sent_at = None


def schedule_daily(db: Any, settings: Any, local_now: datetime | None = None) -> None:
    if settings.environment == "test": return
    local_now = local_now or datetime.now(LOCAL)
    if (local_now.hour, local_now.minute) < (3, 30): return
    if settings.environment == "production" and not settings.source_license_ready(): return
    end = local_now.date() - timedelta(days=1)
    start = end - timedelta(days=6)
    with db.transaction() as session:
        enqueue(session, "collect", {"start": str(start), "end": str(end)}, dedupe=f"daily:{local_now.date()}")


def reminders(db: Any, local_date: Any = None) -> None:
    local_date = local_date or datetime.now(LOCAL).date()
    with db.transaction() as session:
        rows = session.execute(select(Rectification, Inspection).join(Inspection).where(
            Inspection.status.in_(["rectification", "reinspection"]), Rectification.status != "verified",
            Rectification.due_date <= local_date)).all()
        for item, task in rows:
            notify(session, task.assignee_id, "整改到期提醒", f"{task.title} · {item.requirement}", task.id,
                   f"due:{item.id}:{local_date}")


def main() -> None:
    from app.v2.tasks import celery_app
    from app.v2.domains.admin.notification_worker import deliver_pending
    settings = Settings()
    db = Database(settings)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    logging.basicConfig(level=logging.INFO)
    with db.engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(hashtext('platform-scheduler:' || current_schema()))")):
            raise RuntimeError("Another scheduler owns the deployment lock")
        last_maintenance: datetime | None = None
        while not stop.is_set():
            try:
                if last_maintenance is None or now() - last_maintenance > timedelta(minutes=1):
                    recover_stalled(db)
                    schedule_daily(db, settings)
                    reminders(db)
                    deliver_pending(db, settings)
                    last_maintenance = now()
                publish_outbox(db, lambda identifier, queue: celery_app.send_task("platform.run_job", args=[identifier], queue=queue))
                lock.execute(text("SELECT 1"))
            except Exception:
                logger.exception("Scheduler tick failed")
            stop.wait(5)


if __name__ == "__main__":
    main()
