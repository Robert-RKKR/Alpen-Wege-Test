from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.photo import AssetAggPhoto
from app.assets.schemas.asset import PhotoDetail
from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router


@router.get("/{photo_id}", response_model=ApiResponse[PhotoDetail])
async def get_photo(
    photo_id: UUID,
    access: AccessContext = Depends(resource_access("photo", "read")),
    plan: ExpandPlan = Depends(expand_plan(PhotoDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AssetAggPhoto).where(AssetAggPhoto.id == photo_id).options(*plan.load_options(AssetAggPhoto))
    photo = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, photo, not_found_msg="Photo not found")
    return ok(plan.render(photo, viewer=access.user))
