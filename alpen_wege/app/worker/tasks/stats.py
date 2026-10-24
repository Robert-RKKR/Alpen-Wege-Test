# Standard library
import logging
from datetime import datetime, timedelta, timezone

# Third-party
import redis as sync_redis
from celery import shared_task
from sqlalchemy import text

# Local application
from app.worker import model_registry  # noqa: F401
from app.worker.celery_app import celery_app
from app.config import get_settings
from app.database import SyncSessionLocal
from app.explorer.services.track_statistics import (
    recompute_user_statistics as _recompute,
)

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task
def log_active_users():
    with SyncSessionLocal() as session:
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        result = session.execute(
            text(
                "SELECT count(*) FROM profile_usr_user "
                "WHERE last_active_at > :since"
            ),
            {"since": one_hour_ago},
        )
        count = result.scalar()
        logger.info("Active users in the last hour: %d", count)

    return {"active_users": count}


@shared_task(
    bind=True,
    name="stats.recompute_user",
    acks_late=True,
    soft_time_limit=120,
    time_limit=150,
)
def recompute_user_statistics(self, user_id: str):
    try:
        r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.delete(f"stats:pending:{user_id}")
    except Exception:
        logger.warning("Could not delete stats:pending key for %s", user_id)

    with SyncSessionLocal() as session:
        counts = _recompute(session, user_id)
        session.commit()

    logger.info("Stats recompute done for user %s: %s", user_id, counts)
    return {"user_id": user_id, "status": "done", **counts}
