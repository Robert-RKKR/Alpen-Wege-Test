from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.schemas.region import RegionDetail

from ._router import router


@router.get("/{region_id}", response_model=ApiResponse[RegionDetail])
async def get_region(
    region_id: UUID,
    access: AccessContext = Depends(resource_access("region", "read")),
    plan: ExpandPlan = Depends(expand_plan(RegionDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatRegion)
        .where(CompendiumCatRegion.id == region_id)
        .options(*plan.load_options(CompendiumCatRegion))
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="Region not found")
    return ok(plan.render(obj, viewer=access.user))
