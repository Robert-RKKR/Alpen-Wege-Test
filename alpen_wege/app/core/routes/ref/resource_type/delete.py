# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.utils.event_logger import log_deleted
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import require_groups
from app.profile.services.access_cache import invalidate_policy_cache
from app.core.models.resource_type import CoreRefResourceType
from app.profile.models import ProfileUsrUser

from ._router import router


@router.delete("/{item_id}", response_model=ApiResponse[None])
async def delete_resource_type(
    item_id: UUID,
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
    log_deleted(db, obj, admin.id)
    await db.delete(obj)
    await db.commit()
    await invalidate_policy_cache()
    return ok(None, message="Deleted")
