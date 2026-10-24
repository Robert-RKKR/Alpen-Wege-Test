from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion
from app.compendium.schemas.poi_region import PoiRegionRead

from ._router import router
from ._shared import EAGER


@router.get("/{poi_region_id}", response_model=ApiResponse[PoiRegionRead])
async def get_poi_region(
    poi_region_id: UUID,
    access: AccessContext = Depends(resource_access("poi_region", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumM2mPoiRegion)
        .where(CompendiumM2mPoiRegion.id == poi_region_id)
        .options(*EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="POI-Region link not found")
    return ok(obj)
