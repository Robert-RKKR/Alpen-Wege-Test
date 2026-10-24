from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.core.utils.responses import ApiResponse, ok
from app.explorer.schemas.gear import GearRead

from ._router import router


@router.get("/{gear_id}", response_model=ApiResponse[GearRead])
async def get_gear(
    gear_id: UUID,
    access: AccessContext = Depends(resource_access("gear", "read")),
    db: AsyncSession = Depends(get_db),
):
    gear = await db.get(ExplorerAggGear, gear_id)
    check_object_access(access, gear, not_found_msg="Gear not found")
    return ok(gear)
