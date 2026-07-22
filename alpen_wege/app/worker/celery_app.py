from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "alpen_wege",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "cleanup-orphaned-comments-daily": {
            "task": "app.worker.tasks.cleanup.cleanup_orphaned_comments",
            "schedule": crontab(hour=3, minute=0),
        },
        "log-active-users-hourly": {
            "task": "app.worker.tasks.stats.log_active_users",
            "schedule": crontab(minute=0),
        },
    },
)

celery_app.autodiscover_tasks(["app.worker.tasks"])
