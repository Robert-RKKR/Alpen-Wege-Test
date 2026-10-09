# Standard library
import json

# Third-party
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

# Local application
from app.redis import get_redis_pool
from app.profile.models.access_policy import ProfileAccessPolicy
from app.core.models.resource_type import CoreRefResourceType

_CACHE_PREFIX = "access_policy:"
_CACHE_TTL = 300  # 5 minutes


def _cache_key(user_group: str, resource_key: str) -> str:
    return f"{_CACHE_PREFIX}{user_group}:{resource_key}"


async def get_policy_scope(
    user_group: str,
    resource_key: str,
    action: str,
    db: AsyncSession,
) -> str | None:
    redis = get_redis_pool()
    cache_key = _cache_key(user_group, resource_key)

    cached = await redis.get(cache_key)
    if cached is not None:
        policies = json.loads(cached)
        return policies.get(action)

    stmt = (
        select(ProfileAccessPolicy)
        .join(CoreRefResourceType)
        .where(
            ProfileAccessPolicy.user_group == user_group,
            CoreRefResourceType.key == resource_key,
        )
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    policies = {row.action: row.scope for row in rows}
    await redis.set(cache_key, json.dumps(policies), ex=_CACHE_TTL)

    return policies.get(action)


async def invalidate_policy_cache(
    user_group: str | None = None,
    resource_key: str | None = None,
) -> None:
    redis = get_redis_pool()
    if user_group and resource_key:
        await redis.delete(_cache_key(user_group, resource_key))
    else:
        pattern = f"{_CACHE_PREFIX}*"
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=100)
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break
