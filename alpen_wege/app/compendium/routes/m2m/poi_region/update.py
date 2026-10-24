from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion
from app.compendium.schemas.poi_region import PoiRegionRead, PoiRegionUpdate

from ._router import router
from ._shared import EAGER


@router.patch("/{poi_region_id}", response_model=ApiResponse[PoiRegionRead])
async def update_poi_region(
    poi_region_id: UUID,
    body: PoiRegionUpdate,
    access: AccessContext = Depends(resource_access("poi_region", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumM2mPoiRegion, poi_region_id)
    check_object_access(access, obj, not_found_msg="POI-Region link not found")
    changes = body.model_dump(exclude_unset=True)
    old_values = {f: getattr(obj, f) for f in changes}
    for field, value in changes.items():
        setattr(obj, field, value)
    log_updated(db, obj, old_values, changes, access.user.id)
    await db.commit()
    stmt = (
        select(CompendiumM2mPoiRegion)
        .where(CompendiumM2mPoiRegion.id == poi_region_id)
        .options(*EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one())
