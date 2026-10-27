from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.explorer.schemas.gear import GearDetail

from ._router import router


@router.get("/{gear_id}", response_model=ApiResponse[GearDetail])
async def get_gear(
    gear_id: UUID,
    access: AccessContext = Depends(resource_access("gear", "read")),
    plan: ExpandPlan = Depends(expand_plan(GearDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ExplorerAggGear)
        .where(ExplorerAggGear.id == gear_id)
        .options(*plan.load_options(ExplorerAggGear))
    )
    gear = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, gear, not_found_msg="Gear not found")
    return ok(plan.render(gear, viewer=access.user))
