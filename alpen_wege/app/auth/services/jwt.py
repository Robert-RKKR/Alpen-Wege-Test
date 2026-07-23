# Standard library
import uuid
from datetime import datetime, timedelta, timezone

# Third-party
from jose import JWTError, jwt

# Local application
from app.config import get_settings
from app.redis import get_redis_pool

# Cached application settings (JWT secret, algorithm, expiry).
settings = get_settings()

# Redis key prefix under which revoked token IDs (jti) are stored.
_BLACKLIST_PREFIX = "token_blacklist:"


def create_access_token(user_id: uuid.UUID, user_group: str) -> str:
    # Build and sign a JWT access token for a user.
    # Params:
    #   user_id: the authenticated user's UUID (stored in the "sub" claim).
    #   user_group: the user's authorization group (stored in the "group" claim).
    # Returns: the encoded, signed JWT string.
    # Compute issue and expiry timestamps in UTC.
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    # Assemble the claims; "jti" is a unique token id used for revocation.
    payload = {
        "sub": str(user_id),
        "group": user_group,
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    # Sign the payload with the configured secret and algorithm.
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_token(token: str) -> dict:
    # Decode and validate a JWT access token.
    # Params:
    #   token: the encoded JWT string to verify.
    # Returns: the decoded claims dict on success.
    # Raises: ValueError if the token is invalid, expired, or tampered with.
    try:
        # Verify signature and expiry, returning the claims.
        return jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError as e:
        # Normalize library-specific errors into a plain ValueError for callers.
        raise ValueError(str(e)) from e


async def blacklist_token(jti: str, ttl_seconds: int) -> bool:
    # Mark a token id as revoked until it would have expired anyway.
    # Params:
    #   jti: the unique token id ("jti" claim) to revoke.
    #   ttl_seconds: how long to keep the revocation entry (its remaining lifetime).
    # Returns: True if the entry was newly set, False if it already existed.
    redis = get_redis_pool()
    # nx=True only sets the key if absent; ex sets an auto-expiry so it self-cleans.
    return await redis.set(f"{_BLACKLIST_PREFIX}{jti}", "1", ex=ttl_seconds, nx=True)


async def is_token_blacklisted(jti: str) -> bool:
    # Check whether a token id has been revoked.
    # Params:
    #   jti: the unique token id ("jti" claim) to look up.
    # Returns: True if the token is blacklisted, otherwise False.
    redis = get_redis_pool()
    # exists returns the number of matching keys; >0 means the token is revoked.
    return await redis.exists(f"{_BLACKLIST_PREFIX}{jti}") > 0
