from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.schemas.asset import IconDetail
from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router


@router.get("/{icon_id}", response_model=ApiResponse[IconDetail], description="One icon without its SVG text; the picture is `GET /assets/icons/{id}/file`.")
async def get_icon(
    icon_id: UUID,
    access: AccessContext = Depends(resource_access("icon", "read")),
    plan: ExpandPlan = Depends(expand_plan(IconDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AssetAggIcon).where(AssetAggIcon.id == icon_id).options(*plan.load_options(AssetAggIcon))
    icon = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, icon, not_found_msg="Icon not found")
    return ok(plan.render(icon, viewer=access.user))
