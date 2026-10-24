# Standard library
import logging
import time
from typing import Any

# Third-party
from sqlalchemy import select

# Local application
from app.database import AsyncSessionLocal, SyncSessionLocal
from app.management.models.settings import MgmtSettings
from app.management.runtime_settings.registry import REGISTRY, validate_value

logger = logging.getLogger(__name__)

# Values are cached per process. A change applies in the process that handled the
# PATCH at once (invalidate) and in every other process within this many seconds.
CACHE_TTL_S = 30.0

_values: dict[str, Any] = {}
_loaded_at: float | None = None


def _stale() -> bool:
    return _loaded_at is None or (time.monotonic() - _loaded_at) > CACHE_TTL_S


def _store(rows) -> None:
    global _values, _loaded_at
    _values = {key: value for key, value in rows}
    _loaded_at = time.monotonic()


def _backoff() -> None:
    # The table could not be read: keep what we have (or the defaults) and retry after the TTL.
    global _loaded_at
    _loaded_at = time.monotonic()


def invalidate() -> None:
    # Drop the cache so the next read loads from the database.
    global _loaded_at
    _loaded_at = None


def _typed(key: str) -> Any:
    definition = REGISTRY[key]  # unknown key = programming error, raise KeyError
    raw = _values.get(key, definition.default)
    try:
        return validate_value(definition, raw)
    except ValueError:
        logger.warning("Setting %s has an invalid stored value %r, using the default", key, raw)
        return definition.default


def get_setting_sync(key: str) -> Any:
    # Read one setting from a synchronous context (Celery worker, scripts).
    # Params: key: a key from the registry.
    # Returns: the value, or the registry default if the database cannot be read.
    if _stale():
        try:
            with SyncSessionLocal() as session:
                rows = session.execute(select(MgmtSettings.key, MgmtSettings.value)).all()
            _store(rows)
        except Exception:
            logger.warning("Could not read mgmt_settings, using cached or default values", exc_info=True)
            _backoff()
    return _typed(key)


async def get_setting(key: str) -> Any:
    # Read one setting from async code (API routes, WebSocket).
    # Params: key: a key from the registry.
    # Returns: the value, or the registry default if the database cannot be read.
    if _stale():
        try:
            async with AsyncSessionLocal() as session:
                rows = (await session.execute(select(MgmtSettings.key, MgmtSettings.value))).all()
            _store(rows)
        except Exception:
            logger.warning("Could not read mgmt_settings, using cached or default values", exc_info=True)
            _backoff()
    return _typed(key)
