import redis.asyncio as aioredis

from app.redis import get_redis_pool


async def get_redis() -> aioredis.Redis:
    return get_redis_pool()
