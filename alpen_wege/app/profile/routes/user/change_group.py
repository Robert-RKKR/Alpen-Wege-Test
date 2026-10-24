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
from app.profile.models import ProfileUsrUser
from app.profile.schemas import UserRead, AdminGroupUpdate
from app.profile.services import UserService


from ._router import router
from ._shared import user_to_read


@router.put("/{user_id}/group", response_model=ApiResponse[UserRead])
async def change_group(
    user_id: UUID,
    body: AdminGroupUpdate,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    target = await service.get_by_id(user_id)
    if not target or not target.credentials:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No user exists with the given ID.",
        )
    old_group = target.credentials.user_group
    user = await service.set_group(user_id, body.user_group)
    log_updated(db, user, {"user_group": old_group}, {"user_group": body.user_group}, admin.id)
    return ok(user_to_read(user), message="Group updated")
