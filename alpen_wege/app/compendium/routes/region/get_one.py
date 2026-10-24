from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.schemas.region import RegionRead

from ._router import router
from ._shared import EAGER


@router.get("/{region_id}", response_model=ApiResponse[RegionRead])
async def get_region(
    region_id: UUID,
    access: AccessContext = Depends(resource_access("region", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatRegion)
        .where(CompendiumCatRegion.id == region_id)
        .options(*EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="Region not found")
    return ok(obj)
