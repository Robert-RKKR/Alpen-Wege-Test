# Third-party
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.utils.responses import AppError
from app.management.models.settings import MgmtSettings
from app.management.runtime_settings.registry import REGISTRY
from app.management.runtime_settings.service import invalidate
from app.management.utils.event_logger import log_updated
from app.profile.models import ProfileUsrUser
from app.profile.permissions import require_groups


admin_only = require_groups("administrator")


async def get_row(db: AsyncSession, key: str, options=()) -> MgmtSettings:
    definition = REGISTRY.get(key)
    stmt = select(MgmtSettings).where(MgmtSettings.key == key).options(*options)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if definition is None or row is None:
        raise AppError(404, "Not found", error_message="No setting exists with this key.")
    return row


async def apply(db: AsyncSession, row: MgmtSettings, value, admin: ProfileUsrUser) -> MgmtSettings:
    old_values = {"value": row.value}
    row.value = value
    row.updated_by = admin.id
    log_updated(db, row, old_values, {"value": value}, admin.id)
    await db.commit()
    await db.refresh(row)
    invalidate()
    return row
