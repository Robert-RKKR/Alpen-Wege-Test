import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import get_settings
from app.redis import get_redis_pool

settings = get_settings()

_BLACKLIST_PREFIX = "token_blacklist:"


def create_access_token(user_id: uuid.UUID, user_group: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "group": user_group,
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as e:
        raise ValueError(str(e)) from e


async def blacklist_token(jti: str, ttl_seconds: int) -> bool:
    redis = get_redis_pool()
    return await redis.set(f"{_BLACKLIST_PREFIX}{jti}", "1", ex=ttl_seconds, nx=True)


async def is_token_blacklisted(jti: str) -> bool:
    redis = get_redis_pool()
    return await redis.exists(f"{_BLACKLIST_PREFIX}{jti}") > 0
