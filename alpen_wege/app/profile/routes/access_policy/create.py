# Third-party
from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.utils.event_logger import log_created
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import require_groups
from app.profile.services.access_cache import invalidate_policy_cache
from app.core.models.resource_type import CoreRefResourceType
from app.profile.models.access_policy import ProfileAccessPolicy
from app.profile.schemas.access_policy import (
    AccessPolicyCreate,
    AccessPolicyRead,
)
from app.profile.models import ProfileUsrUser

from ._router import router


@router.post(
    "",
    response_model=ApiResponse[AccessPolicyRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_access_policy(
    body: AccessPolicyCreate,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    rt = await db.get(CoreRefResourceType, body.resource_type_id)
    if not rt:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="The referenced resource type does not exist.",
            error_errors=[{"field": "resource_type_id", "code": "not_found", "message": "Resource type does not exist"}],
        )

    existing = await db.execute(
        select(ProfileAccessPolicy).where(
            ProfileAccessPolicy.user_group == body.user_group,
            ProfileAccessPolicy.resource_type_id == body.resource_type_id,
            ProfileAccessPolicy.action == body.action,
        )
    )
    if existing.scalar_one_or_none():
        raise AppError(
            status.HTTP_409_CONFLICT,
            "Duplicate entry",
            error_message="An access policy for this combination already exists.",
            error_errors=[{"field": "user_group+resource_type_id+action", "code": "conflict", "message": "Policy combination already exists"}],
        )

    obj = ProfileAccessPolicy(**body.model_dump())
    db.add(obj)
    await db.flush()
    log_created(db, obj, admin.id)
    await db.commit()
    await db.refresh(obj)
    await invalidate_policy_cache(body.user_group, rt.key)
    return ok(obj, code=201, message="Created")
