# Third-party
from celery import Celery
from celery.schedules import crontab

# Local application
from app.config import get_settings

# Cached application settings (Celery broker/result backend URLs).
settings = get_settings()

# The Celery application instance; broker carries tasks, backend stores
# results.
celery_app = Celery(
    "alpen_wege",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.worker.tasks.cleanup",
        "app.worker.tasks.stats",
        "app.worker.tasks.track_processing",
        "app.worker.tasks.track_detection",
        "app.worker.tasks.management",
    ],
)

# Runtime config: JSON (de)serialization, UTC scheduling, and the periodic beat
# schedule.
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    beat_schedule={
        "cleanup-orphaned-comments-daily": {
            "task": "app.worker.tasks.cleanup.cleanup_orphaned_comments",
            "schedule": crontab(hour=3, minute=0),
        },
        "log-active-users-hourly": {
            "task": "app.worker.tasks.stats.log_active_users",
            "schedule": crontab(minute=0),
        },
        "reap-stuck-tracks": {
            "task": "tracks.reap_stuck",
            "schedule": crontab(minute="*/2"),
        },
        "mgmt-cleanup-retention-daily": {
            "task": "mgmt.cleanup_retention",
            "schedule": crontab(hour=3, minute=30),
        },
        "mgmt-reap-stale-jobs": {
            "task": "mgmt.reap_stale_jobs",
            "schedule": crontab(minute="*/15"),
        },
    },
)

# Auto-import task modules from the tasks package so they register with Celery.
celery_app.autodiscover_tasks(["app.worker.tasks"])
