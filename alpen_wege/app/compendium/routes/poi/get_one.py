from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.compendium.schemas.poi import PoiDetail

from ._router import router


@router.get("/{poi_id}", response_model=ApiResponse[PoiDetail])
async def get_poi(
    poi_id: UUID,
    access: AccessContext = Depends(resource_access("poi", "read")),
    plan: ExpandPlan = Depends(expand_plan(PoiDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatPoi)
        .where(CompendiumCatPoi.id == poi_id)
        .options(*plan.load_options(CompendiumCatPoi))
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="POI not found")
    return ok(plan.render(obj, viewer=access.user))
