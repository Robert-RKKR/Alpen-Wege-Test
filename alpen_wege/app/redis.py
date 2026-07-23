# Third-party
import redis.asyncio as aioredis

# Local application
from app.config import get_settings

# Cached application settings (used for the Redis connection URL).
settings = get_settings()

# Module-level Redis client, created on startup and reused across requests.
redis_pool: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    # Create the shared Redis client and store it at module level.
    # Params: none.
    # Returns: the initialized async Redis client.
    global redis_pool
    # decode_responses=True returns str values instead of bytes.
    redis_pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return redis_pool


async def close_redis() -> None:
    # Close the shared Redis client on shutdown and clear the reference.
    # Params: none.
    # Returns: nothing.
    global redis_pool
    # Only close if a client was actually initialized.
    if redis_pool:
        await redis_pool.close()
        redis_pool = None


def get_redis_pool() -> aioredis.Redis:
    # Accessor for the shared Redis client.
    # Params: none.
    # Returns: the initialized Redis client.
    # Raises: RuntimeError if init_redis() has not been called yet.
    if redis_pool is None:
        raise RuntimeError("Redis not initialized")
    return redis_pool
