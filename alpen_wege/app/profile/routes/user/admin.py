# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.jobs.events import publish_control
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, AppError, ok, ok_list
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser
from app.profile.schemas import UserRead, AdminGroupUpdate
from app.profile.services import UserService


from ._router import router
from ._shared import user_to_read


@router.get("/", response_model=ApiResponse[list[UserRead]])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1),
    is_active: bool | None = None,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    users, total = await service.list_users(skip, limit, is_active)
    items = [user_to_read(u) for u in users]
    return ok_list(items, total=total, limit=limit, offset=skip)


@router.get("/{user_id}", response_model=ApiResponse[UserRead])
async def get_user(
    user_id: UUID,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    user = await service.get_by_id(user_id)
    if not user:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No user exists with the given ID.",
        )
    return ok(user_to_read(user))


@router.put("/{user_id}/activate", response_model=ApiResponse[UserRead])
async def activate_user(
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
    user = await service.set_active(user_id, True)
    log_updated(db, user, old_values, {"is_active": True}, admin.id)
    return ok(user_to_read(user), message="User activated")


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
