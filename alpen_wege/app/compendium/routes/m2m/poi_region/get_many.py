from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion
from app.compendium.schemas.poi_region import PoiRegionRead
from app.core.utils.scope import apply_scope

from ._router import router
from ._shared import EAGER


@router.get("", response_model=ApiResponse[list[PoiRegionRead]])
async def list_poi_regions(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("poi_region", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumM2mPoiRegion)
    count_stmt = apply_scope(count_stmt, CompendiumM2mPoiRegion, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = (
        select(CompendiumM2mPoiRegion)
        .options(*EAGER)
        .order_by(CompendiumM2mPoiRegion.slot_position)
        .limit(limit).offset(offset)
    )
    stmt = apply_scope(stmt, CompendiumM2mPoiRegion, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)
