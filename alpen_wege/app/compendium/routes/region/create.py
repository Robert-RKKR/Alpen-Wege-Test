from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_created
from app.core.utils.responses import ApiResponse, ok
from app.core.schemas.geo import geojson_to_wkt
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.schemas.region import RegionCreate, RegionRead

from ._router import router
from ._shared import EAGER


@router.post("", response_model=ApiResponse[RegionRead], status_code=status.HTTP_201_CREATED)
async def create_region(
    body: RegionCreate,
    access: AccessContext = Depends(resource_access("region", "create")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    if "bbox" in data:
        data["bbox"] = geojson_to_wkt(data["bbox"], "POLYGON")
    obj = CompendiumCatRegion(**data, created_by=access.user.id)
    db.add(obj)
    await db.flush()
    log_created(db, obj, access.user.id)
    await db.commit()
    stmt = (
        select(CompendiumCatRegion)
        .where(CompendiumCatRegion.id == obj.id)
        .options(*EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one(), code=201, message="Created")
