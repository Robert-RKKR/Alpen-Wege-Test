from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.schemas.region import RegionRead
from app.core.utils.scope import apply_scope

from ._router import router
from ._shared import EAGER


@router.get("", response_model=ApiResponse[list[RegionRead]])
async def list_regions(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("region", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumCatRegion)
    count_stmt = apply_scope(count_stmt, CompendiumCatRegion, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = select(CompendiumCatRegion).options(*EAGER).order_by(CompendiumCatRegion.name).limit(limit).offset(offset)
    stmt = apply_scope(stmt, CompendiumCatRegion, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)
