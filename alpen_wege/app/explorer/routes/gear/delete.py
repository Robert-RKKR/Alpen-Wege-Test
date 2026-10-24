from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_deleted
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.core.utils.responses import ApiResponse, ok

from ._router import router


@router.delete("/{gear_id}", response_model=ApiResponse[None])
async def delete_gear(
    gear_id: UUID,
    access: AccessContext = Depends(resource_access("gear", "delete")),
    db: AsyncSession = Depends(get_db),
):
    gear = await db.get(ExplorerAggGear, gear_id)
    check_object_access(access, gear, not_found_msg="Gear not found")
    log_deleted(db, gear, access.user.id)
    await db.delete(gear)
    await db.commit()
    return ok(None, message="Deleted")
