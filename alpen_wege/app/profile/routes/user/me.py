# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, ok
from app.profile.dependencies import get_current_active_user
from app.profile.models import ProfileUsrUser
from app.profile.schemas import UserRead, UserUpdate
from app.profile.services import UserService

from ._router import router
from ._shared import user_to_read


@router.get("/me", response_model=ApiResponse[UserRead])
async def get_me(
    current_user: ProfileUsrUser = Depends(get_current_active_user),
):
    return ok(user_to_read(current_user))


@router.put("/me", response_model=ApiResponse[UserRead])
async def update_me(
    body: UserUpdate,
    current_user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    changes = body.model_dump(exclude_unset=True)
    old_values = {k: getattr(current_user, k) for k in changes}
    updated = await service.update_profile(current_user, changes)
    log_updated(db, updated, old_values, changes, current_user.id)
    return ok(user_to_read(updated), message="Updated")
