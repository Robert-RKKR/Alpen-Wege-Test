# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.jobs.events import publish_control
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser
from app.profile.schemas import UserRead
from app.profile.services import UserService


from ._router import router
from ._shared import user_to_read


@router.put("/{user_id}/deactivate", response_model=ApiResponse[UserRead])
async def deactivate_user(
    user_id: UUID,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    target = await service.get_by_id(user_id)
    if not target:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No user exists with the given ID.",
        )
    old_values = {"is_active": target.is_active}
    user = await service.set_active(user_id, False)
    log_updated(db, user, old_values, {"is_active": False}, admin.id)
    # commit first so the deactivation is visible before the client can ask for a new ticket
    await db.commit()
    await publish_control(user_id, "close", "deactivated")
    return ok(user_to_read(user), message="User deactivated")
