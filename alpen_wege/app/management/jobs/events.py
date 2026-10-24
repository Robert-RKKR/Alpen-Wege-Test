# Standard library
import json
import logging
from datetime import datetime

# Local application
from app.management.schemas.job import JobRead
from app.redis import get_redis_pool, get_sync_redis

logger = logging.getLogger(__name__)

CH_ALL = "aw:all"
TICKET_PREFIX = "aw:ticket:"
CONN_PREFIX = "aw:conns:"


def ch_user(user_id) -> str:
    return f"aw:user:{user_id}"


def ch_job(job_id) -> str:
    return f"aw:job:{job_id}"


def ch_ctl(user_id) -> str:
    return f"aw:ctl:{user_id}"


def job_event(row) -> dict:
    return {"type": "job.update", "job": JobRead.model_validate(row).model_dump(mode="json")}


def progress_event(job_id, stage: str | None, progress: int | None) -> dict:
    return {"type": "job.progress", "job_id": str(job_id), "stage": stage, "progress": progress}


def control_event(action: str, reason: str) -> dict:
    return {"type": "control", "action": action, "reason": reason}


def notice_event(level: str, text: str, expires_at: datetime | None = None) -> dict:
    return {
        "type": "system.notice", "level": level, "text": text,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


def _targets(row: dict) -> list[str]:
    channels = [ch_job(row["id"])]
    if row.get("user_id"):
        channels.append(ch_user(row["user_id"]))
    return channels


def publish_job_event(row: dict) -> None:
    # Synchronous (worker, reaper, scripts). Never raises: the database state is already correct.
    try:
        payload = json.dumps(job_event(row))
        client = get_sync_redis()
        for channel in _targets(row):
            client.publish(channel, payload)
    except Exception:
        logger.warning("Could not publish job event for %s", row.get("id"), exc_info=True)


def publish_progress(user_id, job_id, stage: str | None, progress: int | None) -> None:
    try:
        payload = json.dumps(progress_event(job_id, stage, progress))
        client = get_sync_redis()
        client.publish(ch_job(job_id), payload)
        if user_id:
            client.publish(ch_user(user_id), payload)
    except Exception:
        logger.warning("Could not publish progress for %s", job_id, exc_info=True)


async def publish_job_event_async(row: dict) -> None:
    # Async variant for API routes (job created or failed). Never raises.
    try:
        payload = json.dumps(job_event(row))
        client = get_redis_pool()
        for channel in _targets(row):
            await client.publish(channel, payload)
    except Exception:
        logger.warning("Could not publish job event for %s", row.get("id"), exc_info=True)


async def publish_control(user_id, action: str, reason: str) -> None:
    # Tell every socket of this user to close (logout, deactivation). Never raises.
    try:
        await get_redis_pool().publish(ch_ctl(user_id), json.dumps(control_event(action, reason)))
    except Exception:
        logger.warning("Could not publish control message for %s", user_id, exc_info=True)


async def publish_notice(level: str, text: str, expires_at: datetime | None = None) -> int:
    # Broadcast to every connected socket. Returns the number of sockets that received it.
    return int(await get_redis_pool().publish(CH_ALL, json.dumps(notice_event(level, text, expires_at))))
