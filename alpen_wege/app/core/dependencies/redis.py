# Third-party
import redis.asyncio as aioredis

# Local application
from app.redis import get_redis_pool


async def get_redis() -> aioredis.Redis:
    # FastAPI dependency that provides the shared Redis client.
    # Params: none.
    # Returns: the initialized async Redis client from the connection pool.
    return get_redis_pool()
