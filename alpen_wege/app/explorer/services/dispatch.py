# Standard library
import logging
from uuid import UUID

# Third-party
import redis as sync_redis

# Local application
from app.config import get_settings
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_redis_client: sync_redis.Redis | None = None


def _get_sync_redis() -> sync_redis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = sync_redis.from_url(
            settings.REDIS_URL, decode_responses=True
        )
    return _redis_client


def enqueue_process_track(track_id: UUID, job_id: UUID | None = None) -> str | None:
    # job_id: the mgmt_log_job row of this run; it becomes the Celery task id (None = no job).
    result = celery_app.send_task(
        "tracks.process_gpx",
        args=[str(track_id)],
        task_id=str(job_id) if job_id else None,
        ignore_result=True,
    )
    return result.id if result else None


def enqueue_detect_pois(track_id: UUID, job_id: UUID | str | None = None) -> None:
    # A continuation of an existing job: the job id travels as a keyword argument.
    celery_app.send_task(
        "tracks.detect_pois",
        args=[str(track_id)],
        kwargs={"job_id": str(job_id)} if job_id else None,
        ignore_result=True,
    )


def enqueue_reprocess_track(track_id: UUID, job_id: UUID | None = None) -> None:
    celery_app.send_task(
        "tracks.reprocess",
        args=[str(track_id)],
        task_id=str(job_id) if job_id else None,
        ignore_result=True,
    )


def enqueue_rescan_poi(poi_id: UUID, job_id: UUID | None = None) -> None:
    celery_app.send_task(
        "tracks.rescan_poi",
        args=[str(poi_id)],
        task_id=str(job_id) if job_id else None,
        ignore_result=True,
    )


def enqueue_rescan_card(card_id: UUID, job_id: UUID | None = None) -> None:
    celery_app.send_task(
        "tracks.rescan_card",
        args=[str(card_id)],
        task_id=str(job_id) if job_id else None,
        ignore_result=True,
    )


def request_stats_recompute(user_id: UUID) -> bool:
    settings = get_settings()
    r = _get_sync_redis()
    key = f"stats:pending:{user_id}"
    ttl = settings.STATS_RECOMPUTE_DELAY_S + 60

    was_set = r.set(key, "1", nx=True, ex=ttl)
    if not was_set:
        return False

    try:
        celery_app.send_task(
            "stats.recompute_user",
            args=[str(user_id)],
            countdown=settings.STATS_RECOMPUTE_DELAY_S,
            ignore_result=True,
        )
    except Exception:
        r.delete(key)
        raise

    return True
