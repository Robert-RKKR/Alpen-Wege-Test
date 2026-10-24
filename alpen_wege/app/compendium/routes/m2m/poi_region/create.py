from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_created
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion
from app.compendium.schemas.poi_region import PoiRegionCreate, PoiRegionRead

from ._router import router
from ._shared import EAGER


@router.post("", response_model=ApiResponse[PoiRegionRead], status_code=status.HTTP_201_CREATED)
async def create_poi_region(
    body: PoiRegionCreate,
    access: AccessContext = Depends(resource_access("poi_region", "create")),
    db: AsyncSession = Depends(get_db),
):
    obj = CompendiumM2mPoiRegion(**body.model_dump(exclude_unset=True), created_by=access.user.id)
    db.add(obj)
    await db.flush()
    log_created(db, obj, access.user.id)
    await db.commit()
    stmt = (
        select(CompendiumM2mPoiRegion)
        .where(CompendiumM2mPoiRegion.id == obj.id)
        .options(*EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one(), code=201, message="Created")
