# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import require_groups
from app.core.models.resource_type import CoreRefResourceType
from app.profile.schemas.access_policy import (
    ResourceTypeDetail,
)
from app.profile.models import ProfileUsrUser

from ._router import router


@router.get("/{item_id}", response_model=ApiResponse[ResourceTypeDetail])
async def get_resource_type(
    item_id: UUID,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    plan: ExpandPlan = Depends(expand_plan(ResourceTypeDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CoreRefResourceType)
        .where(CoreRefResourceType.id == item_id)
        .options(*plan.load_options(CoreRefResourceType))
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    if not obj:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No resource type exists with the given ID.",
        )
    return ok(plan.render(obj, viewer=_admin))
