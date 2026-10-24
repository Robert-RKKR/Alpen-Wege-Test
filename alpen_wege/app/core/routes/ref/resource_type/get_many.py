# Third-party
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import require_groups
from app.core.models.resource_type import CoreRefResourceType
from app.profile.schemas.access_policy import (
    ResourceTypeRead,
)
from app.profile.models import ProfileUsrUser

from ._router import router


@router.get("", response_model=ApiResponse[list[ResourceTypeRead]])
async def list_resource_types(
    limit: int = 1000,
    offset: int = 0,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count()).select_from(CoreRefResourceType))).scalar()
    stmt = (
        select(CoreRefResourceType)
        .order_by(CoreRefResourceType.key)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return ok_list(result.scalars().all(), total=total, limit=limit, offset=offset)
