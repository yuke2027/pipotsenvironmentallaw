"""Compatibility facade for the supervised jobs scheduler."""
from app.v2.domains.jobs.scheduler_worker import (
    LOCAL, main, publish_outbox, recover_stalled, reminders, schedule_daily,
)

__all__ = ["LOCAL", "main", "publish_outbox", "recover_stalled", "reminders", "schedule_daily"]

if __name__ == "__main__":
    main()
