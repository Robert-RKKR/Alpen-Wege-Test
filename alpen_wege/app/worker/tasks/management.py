# Standard library
import logging
import time

# Third-party
from celery import shared_task
from sqlalchemy import text

# Local application
from app.worker import model_registry  # noqa: F401
from app.database import SyncSessionLocal
from app.management.jobs import service
from app.management.jobs.events import publish_job_event
from app.management.jobs.tracked_task import TrackedTask, report_progress
from app.management.runtime_settings.service import get_setting_sync

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    base=TrackedTask,
    name="mgmt.demo_job",
    job_stage="working",
    acks_late=True,
    soft_time_limit=300,
    time_limit=330,
)
def demo_job(self, seconds: int = 10, fail: bool = False):
    # Throw-away task to try jobs, progress and the WebSocket without any GPX file.
    seconds = max(1, min(int(seconds), 120))
    for i in range(seconds):
        time.sleep(1)
        report_progress(self, int((i + 1) * 100 / seconds), "working")
        if i + 1 == seconds // 2:
            report_progress(self, 50, "halfway", persist=True)
    if fail:
        raise RuntimeError("demo failure (this text must never reach the client)")
    return {"status": "ok", "seconds": seconds}


BATCH_SIZE = 5000
MAX_BATCHES = 1000  # safety stop: at most 5 million rows per run and table


def _delete_in_batches(sql: str, params: dict) -> int:
    # Delete in small transactions so no long lock is held on a large table.
    total = 0
    for _ in range(MAX_BATCHES):
        with SyncSessionLocal() as session:
            deleted = session.execute(text(sql), {**params, "batch": BATCH_SIZE}).rowcount
            session.commit()
        total += deleted
        if deleted < BATCH_SIZE:
            break
    return total


@shared_task(name="mgmt.cleanup_retention")
def cleanup_retention():
    # Not a job (nobody follows it). Queued and running jobs are never deleted.
    jobs_days = get_setting_sync("jobs.retention_days")
    events_days = get_setting_sync("events.retention_days")
    jobs_deleted = events_deleted = 0

    if jobs_days > 0:
        jobs_deleted = _delete_in_batches(
            "DELETE FROM mgmt_log_job WHERE id IN ("
            "  SELECT id FROM mgmt_log_job"
            "   WHERE status IN ('succeeded', 'failed', 'cancelled')"
            "     AND finished_at < now() - make_interval(days => :days)"
            "   LIMIT :batch)",
            {"days": jobs_days},
        )
    if events_days > 0:
        events_deleted = _delete_in_batches(
            "DELETE FROM mgmt_log_event WHERE id IN ("
            "  SELECT id FROM mgmt_log_event"
            "   WHERE changed_at < now() - make_interval(days => :days)"
            "   LIMIT :batch)",
            {"days": events_days},
        )

    logger.info(
        "Retention: deleted %d job(s) older than %s day(s) and %d event(s) older than %s day(s)",
        jobs_deleted, jobs_days or "forever", events_deleted, events_days or "forever",
    )
    return {"status": "done", "jobs_deleted": jobs_deleted, "events_deleted": events_deleted}


@shared_task(name="mgmt.reap_stale_jobs")
def reap_stale_jobs():
    hours = get_setting_sync("jobs.stale_after_hours")
    if hours <= 0:
        return {"status": "disabled"}
    with SyncSessionLocal() as session:
        rows = service.fail_stale_jobs(session, hours)
        session.commit()
    for row in rows:
        publish_job_event(row)
    if rows:
        logger.warning("Failed %d stale job(s): %s", len(rows), [str(r["id"]) for r in rows])
    return {"status": "done", "failed": len(rows)}
