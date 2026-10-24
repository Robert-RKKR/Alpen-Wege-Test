# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import require_groups
from app.profile.services.access_cache import invalidate_policy_cache
from app.profile.models.access_policy import ProfileAccessPolicy
from app.profile.schemas.access_policy import (
    AccessPolicyRead,
    AccessPolicyUpdate,
)
from app.profile.models import ProfileUsrUser

from ._router import router


@router.patch("/{item_id}", response_model=ApiResponse[AccessPolicyRead])
async def update_access_policy(
    item_id: UUID,
    body: AccessPolicyUpdate,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(ProfileAccessPolicy, item_id)
    if not obj:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No access policy exists with the given ID.",
        )
    old_values = {"scope": obj.scope}
    obj.scope = body.scope
    log_updated(db, obj, old_values, {"scope": body.scope}, admin.id)
    await db.commit()
    await db.refresh(obj)
    await invalidate_policy_cache()
    return ok(obj)
