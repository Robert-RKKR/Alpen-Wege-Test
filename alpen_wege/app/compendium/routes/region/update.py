from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, ok
from app.core.schemas.geo import geojson_to_wkt
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.schemas.region import RegionRead, RegionUpdate

from ._router import router
from ._shared import EAGER


@router.patch("/{region_id}", response_model=ApiResponse[RegionRead])
async def update_region(
    region_id: UUID,
    body: RegionUpdate,
    access: AccessContext = Depends(resource_access("region", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatRegion, region_id)
    check_object_access(access, obj, not_found_msg="Region not found")
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    if "bbox" in data:
        data["bbox"] = geojson_to_wkt(data["bbox"], "POLYGON")
    old_values = {f: getattr(obj, f) for f in data}
    for field, value in data.items():
        setattr(obj, field, value)
    log_updated(db, obj, old_values, data, access.user.id)
    await db.commit()
    stmt = (
        select(CompendiumCatRegion)
        .where(CompendiumCatRegion.id == region_id)
        .options(*EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one())
