# Standard library
import logging

# Third-party
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.management.models.settings import MgmtSettings
from app.management.runtime_settings.registry import REGISTRY, REGISTRY_LIST, validate_value
from app.management.runtime_settings.service import invalidate

logger = logging.getLogger(__name__)


async def seed_settings(session: AsyncSession) -> None:
    # Insert missing settings with their default and refresh type, range, description and
    # default of existing ones. NEVER overwrites `value`.
    result = await session.execute(select(MgmtSettings))
    existing = {row.key: row for row in result.scalars().all()}
    dirty = False

    for d in REGISTRY_LIST:
        row = existing.get(d.key)
        if row is None:
            session.add(MgmtSettings(
                key=d.key, value=d.default, value_type=d.type, default_value=d.default,
                min_value=d.min, max_value=d.max, category=d.category,
                description=d.description, requires_restart=d.requires_restart,
            ))
            dirty = True
            continue
        for attr, new in (
            ("value_type", d.type), ("default_value", d.default),
            ("min_value", d.min), ("max_value", d.max), ("category", d.category),
            ("description", d.description), ("requires_restart", d.requires_restart),
        ):
            if getattr(row, attr) != new:
                setattr(row, attr, new)
                dirty = True
        try:
            validate_value(d, row.value)
        except ValueError as exc:
            logger.warning(
                "Setting %s has an invalid value %r (%s); readers fall back to the default",
                d.key, row.value, exc,
            )

    for key in set(existing) - set(REGISTRY):
        logger.warning("mgmt_settings row %s is not in the registry; kept but unused", key)

    if dirty:
        await session.commit()
    invalidate()
