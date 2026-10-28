from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.services.photo_access import check_photo_link
from app.core.dependencies import get_db
from app.management.utils.event_logger import log_created
from app.core.utils.responses import ApiResponse, ok
from app.core.schemas.geo import geojson_to_wkt
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.compendium.schemas.poi import PoiCreate, PoiRead

from ._router import router
from ._shared import EAGER


@router.post("", response_model=ApiResponse[PoiRead], status_code=status.HTTP_201_CREATED)
async def create_poi(
    body: PoiCreate,
    access: AccessContext = Depends(resource_access("poi", "create")),
    db: AsyncSession = Depends(get_db),
):
    await check_photo_link(db, access.user, body.main_photo_id)
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    obj = CompendiumCatPoi(**data, created_by=access.user.id)
    db.add(obj)
    await db.flush()
    log_created(db, obj, access.user.id)
    await db.commit()
    stmt = (
        select(CompendiumCatPoi)
        .where(CompendiumCatPoi.id == obj.id)
        .options(*EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one(), code=201, message="Created")
