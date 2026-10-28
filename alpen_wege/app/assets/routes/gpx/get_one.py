from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.gpx import AssetAggGpx
from app.assets.schemas.asset import GpxDetail
from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router


@router.get("/{gpx_id}", response_model=ApiResponse[GpxDetail])
async def get_gpx(
    gpx_id: UUID,
    access: AccessContext = Depends(resource_access("gpx", "read")),
    plan: ExpandPlan = Depends(expand_plan(GpxDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AssetAggGpx).where(AssetAggGpx.id == gpx_id).options(*plan.load_options(AssetAggGpx))
    gpx = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, gpx, not_found_msg="GPX file not found")
    return ok(plan.render(gpx, viewer=access.user))
