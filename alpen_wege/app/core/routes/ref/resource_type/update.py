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
from app.core.models.resource_type import CoreRefResourceType
from app.profile.schemas.access_policy import (
    ResourceTypeRead,
    ResourceTypeUpdate,
)
from app.profile.models import ProfileUsrUser

from ._router import router


@router.patch("/{item_id}", response_model=ApiResponse[ResourceTypeRead])
async def update_resource_type(
    item_id: UUID,
    body: ResourceTypeUpdate,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CoreRefResourceType, item_id)
    if not obj:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No resource type exists with the given ID.",
        )
    changes = body.model_dump(exclude_unset=True)
    old_values = {f: getattr(obj, f) for f in changes}
    for field, value in changes.items():
        setattr(obj, field, value)
    log_updated(db, obj, old_values, changes, admin.id)
    await db.commit()
    await db.refresh(obj)
    await invalidate_policy_cache()
    return ok(obj)
