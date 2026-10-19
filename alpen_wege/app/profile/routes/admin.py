# Standard library
from uuid import UUID

# Third-party
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok, ok_list
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser
from app.profile.schemas import UserRead, AdminGroupUpdate
from app.profile.services import UserService
from app.profile.routes.me import _user_to_read

router = APIRouter()


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
    items = [_user_to_read(u) for u in users]
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
    return ok(_user_to_read(user))


@router.put("/{user_id}/activate", response_model=ApiResponse[UserRead])
async def activate_user(
    user_id: UUID,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    user = await service.set_active(user_id, True)
    if not user:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No user exists with the given ID.",
        )
    return ok(_user_to_read(user), message="User activated")


@router.put("/{user_id}/deactivate", response_model=ApiResponse[UserRead])
async def deactivate_user(
    user_id: UUID,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    user = await service.set_active(user_id, False)
    if not user:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No user exists with the given ID.",
        )
    return ok(_user_to_read(user), message="User deactivated")


@router.put("/{user_id}/group", response_model=ApiResponse[UserRead])
async def change_group(
    user_id: UUID,
    body: AdminGroupUpdate,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    user = await service.set_group(user_id, body.user_group)
    if not user:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No user exists with the given ID.",
        )
    return ok(_user_to_read(user), message="Group updated")
