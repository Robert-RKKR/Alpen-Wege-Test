# Standard library
import json
import uuid

# Third-party
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

# Local application
from app.management.models.job import MgmtLogJob
from app.management.runtime_settings.service import get_setting
from app.profile.permissions import require_groups
from app.redis import get_redis_pool


admin_only = require_groups("administrator")


async def cached(key: str, collector):
    # Run a blocking collector in a threadpool; cache the JSON answer in Redis.
    ttl = await get_setting("celery.status_cache_s")
    redis = get_redis_pool()
    if ttl > 0:
        raw = await redis.get(f"aw:celery:{key}")
        if raw:
            return json.loads(raw)
    data = await run_in_threadpool(collector)
    if ttl > 0:
        await redis.set(f"aw:celery:{key}", json.dumps(data), ex=ttl)
    return data


def uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def jobs_by_task_id(db: AsyncSession, task_ids: list[str]) -> dict[str, MgmtLogJob]:
    ids = [u for u in (uuid_or_none(t) for t in task_ids) if u]
    if not ids:
        return {}
    rows = (await db.execute(select(MgmtLogJob).where(MgmtLogJob.id.in_(ids)))).scalars().all()
    return {str(r.id): r for r in rows}
