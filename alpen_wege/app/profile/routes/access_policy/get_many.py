# Third-party
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import require_groups
from app.core.models.resource_type import CoreRefResourceType
from app.profile.models.access_policy import ProfileAccessPolicy
from app.profile.schemas.access_policy import (
    AccessPolicyReadWithKey,
)
from app.profile.models import ProfileUsrUser

from ._router import router


@router.get("", response_model=ApiResponse[list[AccessPolicyReadWithKey]])
async def list_access_policies(
    limit: int = 1000,
    offset: int = 0,
    group: str | None = Query(None),
    resource_key: str | None = Query(None),
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    base = select(ProfileAccessPolicy).join(CoreRefResourceType)
    count_base = select(func.count()).select_from(ProfileAccessPolicy).join(CoreRefResourceType)

    if group:
        base = base.where(ProfileAccessPolicy.user_group == group)
        count_base = count_base.where(ProfileAccessPolicy.user_group == group)
    if resource_key:
        base = base.where(CoreRefResourceType.key == resource_key)
        count_base = count_base.where(CoreRefResourceType.key == resource_key)

    total = (await db.execute(count_base)).scalar()
    stmt = (
        base
        .order_by(ProfileAccessPolicy.user_group, CoreRefResourceType.key, ProfileAccessPolicy.action)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items = []
    for row in rows:
        data = {
            "id": row.id,
            "user_group": row.user_group,
            "resource_type_id": row.resource_type_id,
            "action": row.action,
            "scope": row.scope,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "resource_key": row.resource_type.key if row.resource_type else None,
        }
        items.append(AccessPolicyReadWithKey(**data))

    return ok_list(items, total=total, limit=limit, offset=offset)
