from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_updated
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.core.utils.responses import ApiResponse, ok
from app.explorer.schemas.gear import GearRead, GearUpdate

from ._router import router


@router.patch("/{gear_id}", response_model=ApiResponse[GearRead])
async def update_gear(
    gear_id: UUID,
    body: GearUpdate,
    access: AccessContext = Depends(resource_access("gear", "update")),
    db: AsyncSession = Depends(get_db),
):
    gear = await db.get(ExplorerAggGear, gear_id)
    check_object_access(access, gear, not_found_msg="Gear not found")
    changes = body.model_dump(exclude_unset=True)
    old_values = {f: getattr(gear, f) for f in changes}
    for field, value in changes.items():
        setattr(gear, field, value)
    log_updated(db, gear, old_values, changes, access.user.id)
    await db.commit()
    await db.refresh(gear)
    return ok(gear)
